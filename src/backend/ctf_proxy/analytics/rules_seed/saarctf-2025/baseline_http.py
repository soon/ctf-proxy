from collections.abc import Iterable

from ctf_proxy.analytics.context import RequestContext
from ctf_proxy.analytics.rule import Match, PatternRule


class RouterploitAccountGuid(PatternRule):
    name = "routerploit_account_guid"
    port = 80

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        path = ctx.path.lower()
        if path.startswith("/account.php") and "user_guid=" in path:
            yield Match(tag="idor", meta=ctx.path)


class RouterploitAuthCode(PatternRule):
    name = "routerploit_auth_code"
    port = 80

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        path = ctx.path.lower()
        if path.startswith("/admin/business_requests.php") and "auth_code=" in path:
            yield Match(tag="auth_bypass", meta=ctx.path)


class RouterploitForwardedFor(PatternRule):
    name = "routerploit_forwarded_for"
    port = 80

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        xff = ctx.request_header("x-forwarded-for")
        if xff:
            yield Match(tag="header_spoof", meta=f"X-Forwarded-For: {xff}")


class SlcgMaxIdProbe(PatternRule):
    name = "slcg_max_id_probe"
    port = 51349

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        if ctx.path.split("?")[0] == "/data/max_id":
            yield Match(tag="enumeration", meta=ctx.path)


class NoServiceRetrieveDenied(PatternRule):
    name = "no_service_retrieve_denied"
    port = 6666

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        if "/retrieve/" in ctx.path and ctx.status in (403, 418):
            yield Match(tag="token_bruteforce", meta=f"{ctx.status} {ctx.path.split('?')[0]}")
