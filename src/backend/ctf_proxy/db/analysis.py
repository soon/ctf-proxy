import logging
import os

from ctf_proxy.db import connection
from ctf_proxy.db.tables.analysis_cursor import AnalysisCursorTable
from ctf_proxy.db.tables.backfill_job import BackfillJobTable
from ctf_proxy.db.tables.http_analysis_result import HttpAnalysisResultTable
from ctf_proxy.db.tables.rule import RuleTable
from ctf_proxy.db.tables.rule_source import RuleSourceTable
from ctf_proxy.db.tables.tcp_analysis_result import TcpAnalysisResultTable

logger = logging.getLogger(__name__)


class AnalysisDB:
    def __init__(self):
        self.rules = RuleTable()
        self.http_results = HttpAnalysisResultTable()
        self.tcp_results = TcpAnalysisResultTable()
        self.cursors = AnalysisCursorTable()
        self.backfill = BackfillJobTable()
        self.rules_source = RuleSourceTable()

    def connect(self):
        return connection.connect()

    def init_schema(self, schema_file: str | None = None) -> None:
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "analysis_schema.sql")

        dashboard_file = os.path.join(os.path.dirname(__file__), "dashboard_schema.sql")

        with open(schema_file) as f:
            schema_sql = f.read()

        with open(dashboard_file) as f:
            dashboard_sql = f.read()

        with self.connect() as conn:
            conn.execute(schema_sql)
            conn.execute(dashboard_sql)
            conn.commit()

        logger.info(f"Analysis database schema initialized from {schema_file}")

    def init_db(self) -> None:
        self.init_schema()
        logger.info(f"Analysis database initialized: {connection.describe()}")

    def tag_stats(self, port: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.name AS rule, s.tag AS tag, s.source AS source, SUM(s.count) AS n
                FROM tag_time_stats s
                JOIN rule r ON r.id = s.rule_id
                WHERE s.port = %s
                GROUP BY r.name, s.tag, s.source
                """,
                (port,),
            ).fetchall()

        merged: dict[tuple[str, str], dict] = {}
        for rule, tag, source, n in rows:
            entry = merged.setdefault(
                (rule, tag), {"rule": rule, "tag": tag, "http_count": 0, "tcp_count": 0, "total": 0}
            )
            entry[f"{source}_count"] += n
            entry["total"] += n
        return sorted(merged.values(), key=lambda e: e["total"], reverse=True)

    def tag_time_series(self, port: int, since: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.name AS rule, s.tag AS tag, s.time AS time, SUM(s.count) AS n
                FROM tag_time_stats s
                JOIN rule r ON r.id = s.rule_id
                WHERE s.port = %s AND s.time >= %s
                GROUP BY r.name, s.tag, s.time
                ORDER BY s.time
                """,
                (port, since),
            ).fetchall()

        series: dict[tuple[str, str], dict] = {}
        for rule, tag, time, n in rows:
            entry = series.setdefault(
                (rule, tag), {"rule": rule, "tag": tag, "total": 0, "time_series": []}
            )
            entry["time_series"].append({"timestamp": time, "count": n})
            entry["total"] += n
        return sorted(series.values(), key=lambda e: e["total"], reverse=True)

    def analysis_for_ref(self, source_type: str, ref_id: int) -> list[dict]:
        table = "http_analysis_result" if source_type == "http" else "tcp_analysis_result"
        ref_column = "http_request_id" if source_type == "http" else "tcp_connection_id"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.name AS rule, res.tag AS tag, res.meta AS meta
                FROM {table} res
                JOIN rule r ON r.id = res.rule_id
                WHERE res.{ref_column} = %s
                ORDER BY res.id
                """,
                (ref_id,),
            ).fetchall()
        return [{"rule": row[0], "tag": row[1], "meta": row[2]} for row in rows]

    def tags_for_refs(
        self, source_type: str, ids: list[int], rules: list[str] | None
    ) -> dict[int, list[str]]:
        if not ids:
            return {}
        table = "http_analysis_result" if source_type == "http" else "tcp_analysis_result"
        ref_column = "http_request_id" if source_type == "http" else "tcp_connection_id"
        id_placeholders = ",".join(["%s"] * len(ids))
        params: list = list(ids)
        rule_clause = ""
        if rules:
            rule_placeholders = ",".join(["%s"] * len(rules))
            rule_clause = f" AND r.name IN ({rule_placeholders})"
            params.extend(rules)

        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT res.{ref_column} AS ref_id, res.tag AS tag
                FROM {table} res
                JOIN rule r ON r.id = res.rule_id
                WHERE res.{ref_column} IN ({id_placeholders}){rule_clause}
                ORDER BY res.id
                """,
                params,
            ).fetchall()

        result: dict[int, list[str]] = {}
        for ref_id, tag in rows:
            tags = result.setdefault(ref_id, [])
            if tag not in tags:
                tags.append(tag)
        return result


def make_analysis_db() -> AnalysisDB:
    db = AnalysisDB()
    db.init_db()
    return db
