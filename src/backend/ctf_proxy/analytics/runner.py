import logging
import os
import signal
import sys
import threading

from ctf_proxy.analytics.db import AnalysisResultRow, make_analysis_db
from ctf_proxy.analytics.registry import RuleRegistry
from ctf_proxy.analytics.source import SourceReader
from ctf_proxy.db import connection
from ctf_proxy.db.utils import now_timestamp

DEFAULT_BATCH_SIZE = 500
SLEEP_BETWEEN_BATCHES = 1
SLEEP_ON_ERROR = 5

HTTP_SOURCE = "http_request"
TCP_SOURCE = "tcp_connection"

logger = logging.getLogger(__name__)


class AnalyzerRunner:
    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.source = SourceReader()
        self.db = make_analysis_db()
        self.registry = RuleRegistry(self.db)
        self.batch_size = batch_size
        self.rule_ids: dict[str, int] = {}
        self.running = True
        self.shutdown_event = threading.Event()

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame_):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        self.shutdown_event.set()

    def wait_or_shutdown(self, duration) -> bool:
        return self.shutdown_event.wait(timeout=duration)

    def rule_id(self, tx, name: str) -> int:
        cached = self.rule_ids.get(name)
        if cached is not None:
            return cached
        resolved = self.db.rules.get_or_create(tx, name)
        self.rule_ids[name] = resolved
        return resolved

    def run_rules(self, contexts, source: str, matcher_attr: str, group) -> list[AnalysisResultRow]:
        results: list[AnalysisResultRow] = []
        for ctx in contexts:
            for rule, rule_id in group:
                if rule.port is not None and rule.port != ctx.port:
                    continue
                name = rule.rule_name()
                try:
                    for match in getattr(rule, matcher_attr)(ctx) or []:
                        results.append(
                            AnalysisResultRow(
                                rule_id=rule_id,
                                tag=match.tag,
                                meta=match.meta,
                                port=ctx.port,
                                ref_id=ctx.id,
                                batch_id=ctx.batch_id,
                                event_time=ctx.start_time,
                            )
                        )
                except Exception:
                    logger.exception(f"Rule {name} failed on {source} {ctx.id}")
        return results

    def process_source(self, tx, source, read_fn, matcher_attr, result_table) -> int:
        rules = self.registry.rules
        if not rules:
            return 0

        groups: dict[int, list] = {}
        for rule in rules:
            rule_id = self.rule_id(tx, rule.rule_name())
            last_id = self.db.cursors.get(tx, rule_id, source)
            groups.setdefault(last_id, []).append((rule, rule_id))

        processed = 0
        created = now_timestamp()
        for last_id, group in sorted(groups.items()):
            contexts = read_fn(last_id, self.batch_size)
            if not contexts:
                continue

            results = self.run_rules(contexts, source, matcher_attr, group)
            max_id = max(ctx.id for ctx in contexts)

            if results:
                result_table.insert_many(tx, results, created)
            for _, rule_id in group:
                self.db.cursors.set(tx, rule_id, source, max_id)
            processed += len(contexts)

        return processed

    def process_batch(self) -> int:
        with self.db.connect() as conn:
            tx = conn.cursor()
            processed = self.process_source(
                tx, HTTP_SOURCE, self.source.read_http_batch, "match", self.db.http_results
            )
            processed += self.process_source(
                tx, TCP_SOURCE, self.source.read_tcp_batch, "match_tcp", self.db.tcp_results
            )
            conn.commit()

        return processed

    def run_all_rules(self, contexts, source: str, matcher_attr: str, tx) -> list[AnalysisResultRow]:
        group = [(rule, self.rule_id(tx, rule.rule_name())) for rule in self.registry.rules]
        return self.run_rules(contexts, source, matcher_attr, group)

    def backfill_source(self, tx, job, read_fn, matcher_attr, result_table, source) -> int:
        cursor = job.http_cursor if source == HTTP_SOURCE else job.tcp_cursor
        contexts = read_fn(cursor, job.target_id, job.ports, self.batch_size)
        if not contexts:
            return 0

        results = self.run_all_rules(contexts, source, matcher_attr, tx)
        max_id = max(ctx.id for ctx in contexts)
        result_table.delete_for_refs(tx, [ctx.id for ctx in contexts])
        if results:
            result_table.insert_many(tx, results, now_timestamp())
        column = "http_cursor" if source == HTTP_SOURCE else "tcp_cursor"
        self.db.backfill.update(tx, job.id, now_timestamp(), status="running", **{column: max_id})
        return len(contexts)

    def process_backfill_batch(self) -> int:
        with self.db.connect() as conn:
            tx = conn.cursor()
            job = self.db.backfill.active(tx)
            if job is None:
                return 0

            processed = self.backfill_source(
                tx, job, self.source.read_http_backfill, "match", self.db.http_results, HTTP_SOURCE
            )
            if processed == 0:
                processed = self.backfill_source(
                    tx, job, self.source.read_tcp_backfill, "match_tcp", self.db.tcp_results, TCP_SOURCE
                )
            if processed == 0:
                self.db.backfill.update(tx, job.id, now_timestamp(), status="done")
            conn.commit()

        return processed

    def process_loop(self) -> None:
        while self.running:
            try:
                self.registry.maybe_reload()
                processed = self.process_batch()
                processed += self.process_backfill_batch()
                if processed:
                    logger.info(f"Processed {processed} row(s)")
                if processed >= self.batch_size:
                    continue
                if self.wait_or_shutdown(SLEEP_BETWEEN_BATCHES):
                    break
            except Exception:
                logger.exception("Unable to process analyzer batch")
                if self.wait_or_shutdown(SLEEP_ON_ERROR):
                    break

    def run(self) -> None:
        logger.info("Starting analyzer...")
        logger.info(f"Database: {connection.describe()}")

        self.registry.maybe_reload()
        try:
            self.process_loop()
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Analyzer stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    batch_size = int(os.environ.get("BATCH_SIZE", DEFAULT_BATCH_SIZE))

    runner = AnalyzerRunner(batch_size)
    runner.run()
