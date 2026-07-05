from dataclasses import dataclass

from ctf_proxy.analyzer.registry import load_rules_from_source
from ctf_proxy.analyzer.source import SourceReader

HTTP = "http"
TCP = "tcp"


@dataclass
class PreviewMatch:
    rule: str
    tag: str
    meta: str
    port: int
    ref_id: int


@dataclass
class PreviewResult:
    matches: list[PreviewMatch]
    scanned: int


class PreviewRunner:
    def __init__(self, source_db_file: str):
        self.source = SourceReader(source_db_file)

    def preview(self, source_code: str, source_type: str, ids: list[int]) -> PreviewResult:
        rules = load_rules_from_source(source_code, "ctf_proxy_analyzer_preview")

        if source_type == TCP:
            contexts = self.source.read_tcp_by_ids(ids)
            matcher_attr = "match_tcp"
        else:
            contexts = self.source.read_http_by_ids(ids)
            matcher_attr = "match"

        matches: list[PreviewMatch] = []
        for ctx in contexts:
            for rule in rules:
                if rule.port is not None and rule.port != ctx.port:
                    continue
                for match in getattr(rule, matcher_attr)(ctx) or []:
                    matches.append(
                        PreviewMatch(
                            rule=rule.rule_name(),
                            tag=match.tag,
                            meta=match.meta,
                            port=ctx.port,
                            ref_id=ctx.id,
                        )
                    )
        return PreviewResult(matches=matches, scanned=len(contexts))
