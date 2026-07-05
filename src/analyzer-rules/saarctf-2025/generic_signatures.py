from collections.abc import Iterable

from ctf_proxy.analyzer.context import ConnectionContext, RequestContext
from ctf_proxy.analyzer.rule import Match, PatternRule

TRAVERSAL_MARKERS = ("../", "..\\", "..%2f", "%2e%2e/", "%2e%2e%2f")
SQLI_MARKERS = ("' or '1'='1", "union select", "or 1=1", "sleep(", "'--", "database_to_xml", "::text::int")
SHELL_MARKERS = ("/bin/sh", "/bin/bash", "cat flag", "cat /flag", "cat /etc", "; cat ", "&& cat ", "; id", "$(cat")
FORMAT_STRING = ("%p%p", "%x%x", "%n", "%08x", "%s%s%s")


class HttpPathTraversal(PatternRule):
    name = "http_path_traversal"

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        haystack = f"{ctx.path} {ctx.body or ''}".lower()
        for marker in TRAVERSAL_MARKERS:
            if marker in haystack:
                yield Match(tag="path_traversal", meta=marker)
                return


class HttpSqli(PatternRule):
    name = "http_sqli"

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        haystack = f"{ctx.path} {ctx.body or ''}".lower()
        for marker in SQLI_MARKERS:
            if marker in haystack:
                yield Match(tag="sqli", meta=marker)
                return


class ServerError(PatternRule):
    name = "server_error"

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        if ctx.status is not None and ctx.status >= 500:
            yield Match(tag="server_error", meta=str(ctx.status))


class AuthDenied(PatternRule):
    name = "auth_denied"

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        if ctx.status in (401, 403):
            yield Match(tag="auth_denied", meta=f"{ctx.status} {ctx.path.split('?')[0]}")


class TcpPathTraversal(PatternRule):
    name = "tcp_path_traversal"

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        haystack = ctx.read_text.lower()
        for marker in TRAVERSAL_MARKERS:
            if marker in haystack:
                yield Match(tag="path_traversal", meta=marker)
                return


class TcpShell(PatternRule):
    name = "tcp_shell"

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        haystack = ctx.read_text.lower()
        for marker in SHELL_MARKERS:
            if marker in haystack:
                yield Match(tag="tcp_shell", meta=marker)
                return


class TcpFormatString(PatternRule):
    name = "tcp_format_string"

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        haystack = ctx.read_text.lower()
        for marker in FORMAT_STRING:
            if marker in haystack:
                yield Match(tag="format_string", meta=marker)
                return


class TcpBinaryPayload(PatternRule):
    name = "tcp_binary_payload"

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        text = ctx.read_text
        if not text:
            return
        nonprintable = sum(1 for ch in text if ord(ch) < 9 or 13 < ord(ch) < 32)
        if nonprintable >= 8:
            yield Match(tag="binary_payload", meta=str(nonprintable))
