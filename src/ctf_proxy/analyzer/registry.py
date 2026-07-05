import importlib.util
import inspect
import logging
import sys
from pathlib import Path

from ctf_proxy.analyzer.rule import PatternRule

logger = logging.getLogger(__name__)


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
    def __init__(self, rules_folder: str):
        self.rules_folder = Path(rules_folder)
        self.rules: list[PatternRule] = []
        self.signature: dict[str, float] = {}

    def rule_files(self) -> list[Path]:
        if not self.rules_folder.exists():
            return []
        return sorted(p for p in self.rules_folder.glob("*.py") if p.name != "__init__.py")

    def folder_signature(self) -> dict[str, float]:
        return {str(path): path.stat().st_mtime for path in self.rule_files()}

    def maybe_reload(self) -> bool:
        signature = self.folder_signature()
        if signature == self.signature:
            return False
        self.signature = signature
        self.load()
        return True

    def load(self) -> None:
        rules: list[PatternRule] = []
        for path in self.rule_files():
            try:
                rules.extend(self.load_file(path))
            except Exception:
                logger.exception(f"Failed to load rules from {path}")
        self.rules = rules
        logger.info(f"Loaded {len(rules)} rule(s) from {self.rules_folder}")

    def load_file(self, path: Path) -> list[PatternRule]:
        module_name = f"ctf_proxy_analyzer_rules_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        rules: list[PatternRule] = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, PatternRule)
                and obj is not PatternRule
                and obj.__module__ == module_name
            ):
                rules.append(obj())
        return rules
