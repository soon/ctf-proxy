from ctf_proxy.analytics.rule import Match, PatternRule

ADMIN_MARKERS = ("/admin", "/debug", "/.env", "/actuator")


class AdminProbe(PatternRule):
    name = "admin_probe"

    def match(self, ctx):
        lowered = ctx.path.lower()
        for marker in ADMIN_MARKERS:
            if lowered.startswith(marker):
                yield Match(tag="admin_probe", meta=ctx.path)
                return
