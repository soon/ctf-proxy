from ctf_proxy.analyzer.rule import Match, PatternRule


class MyRule(PatternRule):
    name = "my_rule"
    port = 80  # optional: restrict to one service; omit to apply to all ports

    def match(self, ctx):
        if "/admin" in (ctx.path or ""):
            yield Match(tag="is_admin", meta=ctx.path)
