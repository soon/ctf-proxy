import logging

from ctf_proxy.analytics.rule import PatternRule
from ctf_proxy.db.analysis import AnalysisDB

logger = logging.getLogger(__name__)

DRAFT = "draft"
ENABLED = "enabled"


def extract_rules(members, module_name: str) -> list[PatternRule]:
    rules: list[PatternRule] = []
    for obj in members:
        if (
            isinstance(obj, type)
            and issubclass(obj, PatternRule)
            and obj is not PatternRule
            and obj.__module__ == module_name
        ):
            rules.append(obj())
    return rules


def load_rules_from_source(
    code: str, module_name: str = "ctf_proxy_analyzer_inline"
) -> list[PatternRule]:
    namespace = {"__name__": module_name}
    exec(compile(code, f"<{module_name}>", "exec"), namespace)
    return extract_rules(namespace.values(), module_name)


class RuleRegistry:
    def __init__(self, db: AnalysisDB):
        self.db = db
        self.rules: list[PatternRule] = []
        self.last_updated: int = 0

    def enabled_updated(self) -> int:
        with self.db.connect() as conn:
            return self.db.rules_source.max_updated(conn.cursor(), ENABLED)

    def enabled_rows(self) -> list:
        with self.db.connect() as conn:
            return self.db.rules_source.list(conn.cursor(), ENABLED)

    def maybe_reload(self) -> bool:
        latest = self.enabled_updated()
        if latest == self.last_updated:
            return False
        self.last_updated = latest
        self.load()
        return True

    def load(self) -> None:
        rules: list[PatternRule] = []
        for name, _status, source in self.enabled_rows():
            try:
                rules.extend(load_rules_from_source(source, f"ctf_proxy_analyzer_rules_{name}"))
            except Exception:
                logger.exception(f"Failed to load rules from {name}")
        self.rules = rules
        logger.info(f"Loaded {len(rules)} rule(s) from database")
