from collections.abc import Iterable
from dataclasses import dataclass

from ctf_proxy.analytics.context import ConnectionContext, RequestContext


@dataclass
class Match:
    tag: str
    meta: str = ""


class PatternRule:
    name: str = ""
    port: int | None = None

    def match(self, ctx: RequestContext) -> Iterable[Match] | None:
        return None

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match] | None:
        return None

    def rule_name(self) -> str:
        return self.name or type(self).__name__
