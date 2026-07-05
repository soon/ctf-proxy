import re
from dataclasses import dataclass

from ctf_proxy.analytics.registry import DRAFT, ENABLED, load_rules_from_source
from ctf_proxy.db.analysis import AnalysisDB

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class RuleValidationError(ValueError):
    pass


@dataclass
class RuleInfo:
    name: str
    status: str
    port: int | None
    error: str | None


class RulesStore:
    def __init__(self, db: AnalysisDB):
        self.db = db

    def validate_name(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise ValueError(f"Invalid rule name: {name}")

    def validate_status(self, status: str) -> None:
        if status not in (DRAFT, ENABLED):
            raise ValueError(f"Invalid status: {status}")

    def parse_port(self, source: str, label: str) -> tuple[int | None, str | None]:
        try:
            rules = load_rules_from_source(source, f"rule_meta_{label}")
        except Exception as e:
            return None, str(e)
        if not rules:
            return None, "No PatternRule subclass defined"
        ports = {rule.port for rule in rules}
        return (next(iter(ports)) if len(ports) == 1 else None), None

    def validate_source(self, source: str) -> None:
        try:
            rules = load_rules_from_source(source, "rule_validate")
        except Exception as e:
            raise RuleValidationError(f"Rule does not compile: {e}") from e
        if not rules:
            raise RuleValidationError("Source does not define a PatternRule subclass")

    def next_updated(self, tx) -> int:
        return self.db.rules_source.max_updated(tx) + 1

    def list_rules(self, port: int | None = None) -> list[RuleInfo]:
        with self.db.connect() as conn:
            rows = self.db.rules_source.list(conn.cursor())
        infos: list[RuleInfo] = []
        for name, status, source in rows:
            rule_port, error = self.parse_port(source, f"{status}_{name}")
            infos.append(RuleInfo(name=name, status=status, port=rule_port, error=error))
        if port is not None:
            infos = [info for info in infos if info.port is None or info.port == port]
        return infos

    def get_source(self, name: str, status: str) -> str:
        self.validate_name(name)
        with self.db.connect() as conn:
            source = self.db.rules_source.get(conn.cursor(), name, status)
        if source is None:
            raise FileNotFoundError(f"Rule not found: {status}/{name}")
        return source

    def save_draft(self, name: str, source: str) -> None:
        self.validate_name(name)
        self.validate_source(source)
        with self.db.connect() as conn:
            tx = conn.cursor()
            self.db.rules_source.upsert(tx, name, DRAFT, source, self.next_updated(tx))
            conn.commit()

    def delete_rule(self, name: str, status: str) -> None:
        self.validate_name(name)
        with self.db.connect() as conn:
            tx = conn.cursor()
            deleted = self.db.rules_source.delete(tx, name, status)
            conn.commit()
        if not deleted:
            raise FileNotFoundError(f"Rule not found: {status}/{name}")

    def promote(self, name: str) -> None:
        self.validate_name(name)
        with self.db.connect() as conn:
            tx = conn.cursor()
            source = self.db.rules_source.get(tx, name, DRAFT)
            if source is None:
                raise FileNotFoundError(f"Draft rule not found: {name}")
            self.validate_source(source)
            self.db.rules_source.promote(tx, name)
            conn.commit()
