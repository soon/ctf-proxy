import re
from dataclasses import dataclass
from pathlib import Path

from ctf_proxy.analyzer.registry import load_rules_from_source

DRAFT = "draft"
ENABLED = "enabled"
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
    def __init__(self, rules_folder: str):
        self.enabled_folder = Path(rules_folder)
        self.preview_folder = self.enabled_folder / "preview"

    def folder(self, status: str) -> Path:
        if status == DRAFT:
            return self.preview_folder
        if status == ENABLED:
            return self.enabled_folder
        raise ValueError(f"Invalid status: {status}")

    def validate_name(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise ValueError(f"Invalid rule name: {name}")

    def path(self, name: str, status: str) -> Path:
        self.validate_name(name)
        return self.folder(status) / f"{name}.py"

    def parse_port(self, source: str, label: str) -> tuple[int | None, str | None]:
        try:
            rules = load_rules_from_source(source, f"rule_meta_{label}")
        except Exception as e:
            return None, str(e)
        if not rules:
            return None, "No PatternRule subclass defined"
        ports = {rule.port for rule in rules}
        return (next(iter(ports)) if len(ports) == 1 else None), None

    def describe(self, path: Path, status: str) -> RuleInfo:
        port, error = self.parse_port(path.read_text(), f"{status}_{path.stem}")
        return RuleInfo(name=path.stem, status=status, port=port, error=error)

    def list_folder(self, folder: Path, status: str) -> list[RuleInfo]:
        if not folder.exists():
            return []
        return [
            self.describe(path, status)
            for path in sorted(folder.glob("*.py"))
            if path.name != "__init__.py"
        ]

    def list_rules(self, port: int | None = None) -> list[RuleInfo]:
        infos = self.list_folder(self.enabled_folder, ENABLED)
        infos += self.list_folder(self.preview_folder, DRAFT)
        if port is not None:
            infos = [info for info in infos if info.port is None or info.port == port]
        return infos

    def get_source(self, name: str, status: str) -> str:
        path = self.path(name, status)
        if not path.exists():
            raise FileNotFoundError(f"Rule not found: {status}/{name}")
        return path.read_text()

    def validate_source(self, source: str) -> None:
        try:
            rules = load_rules_from_source(source, "rule_validate")
        except Exception as e:
            raise RuleValidationError(f"Rule does not compile: {e}") from e
        if not rules:
            raise RuleValidationError("Source does not define a PatternRule subclass")

    def save_draft(self, name: str, source: str) -> None:
        self.validate_name(name)
        self.validate_source(source)
        self.preview_folder.mkdir(parents=True, exist_ok=True)
        self.path(name, DRAFT).write_text(source)

    def delete_rule(self, name: str, status: str) -> None:
        path = self.path(name, status)
        if not path.exists():
            raise FileNotFoundError(f"Rule not found: {status}/{name}")
        path.unlink()

    def promote(self, name: str) -> None:
        source_path = self.path(name, DRAFT)
        if not source_path.exists():
            raise FileNotFoundError(f"Draft rule not found: {name}")
        self.validate_source(source_path.read_text())
        self.enabled_folder.mkdir(parents=True, exist_ok=True)
        source_path.replace(self.path(name, ENABLED))
