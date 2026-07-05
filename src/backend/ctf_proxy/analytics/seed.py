import logging
from pathlib import Path

from ctf_proxy.analytics.registry import DRAFT, ENABLED
from ctf_proxy.db.analysis import AnalysisDB, make_analysis_db

logger = logging.getLogger(__name__)


def rule_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.glob("*.py") if p.name != "__init__.py")


def seed_rules(db: AnalysisDB, seed_dir: Path) -> int:
    enabled = rule_files(seed_dir)
    drafts = rule_files(seed_dir / "preview")
    with db.connect() as conn:
        tx = conn.cursor()
        updated = db.rules_source.max_updated(tx) + 1
        for path in enabled:
            db.rules_source.upsert(tx, path.stem, ENABLED, path.read_text(), updated)
            updated += 1
        for path in drafts:
            db.rules_source.upsert(tx, path.stem, DRAFT, path.read_text(), updated)
            updated += 1
        conn.commit()
    count = len(enabled) + len(drafts)
    logger.info(f"Seeded {count} rule(s) from {seed_dir}")
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    seed_dir = Path(__file__).parent / "rules_seed"
    db = make_analysis_db()
    seed_rules(db, seed_dir)


if __name__ == "__main__":
    main()
