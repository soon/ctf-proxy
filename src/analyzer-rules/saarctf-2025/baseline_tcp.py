from collections.abc import Iterable

from ctf_proxy.analyzer.context import ConnectionContext
from ctf_proxy.analyzer.rule import Match, PatternRule


class RceaasJailEscape(PatternRule):
    name = "rceaas_jail_escape"
    port = 1835

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        haystack = ctx.read_text.lower()
        for marker in ("set cwd=", "set username=", "passwords/."):
            if marker in haystack:
                yield Match(tag="jail_escape", meta=marker)
                return


class BlockRopeLogAccount(PatternRule):
    name = "blockrope_log_account"
    port = 1337

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        haystack = ctx.read_text.lower()
        if "logs/" in haystack or ".log" in haystack:
            yield Match(tag="log_traversal", meta="logs/")
