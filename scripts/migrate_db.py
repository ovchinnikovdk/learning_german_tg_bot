"""DB migration script — safe to run multiple times (idempotent).

Run from the project root:
    .venv/bin/python scripts/migrate_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinydb import TinyDB, Query

DB_PATH = Path(__file__).parent.parent / "data" / "db.json"
_Q = Query()


def migrate(db: TinyDB) -> None:
    _migrate_candidate_source(db)
    _migrate_answers_date(db)
    _migrate_custom_questions_fields(db)


# ------------------------------------------------------------------
# candidates: normalise old source value "llm" → "local"
# ------------------------------------------------------------------

def _migrate_candidate_source(db: TinyDB) -> None:
    table = db.table("question_candidates")
    stale = table.search(_Q.source == "llm")
    if not stale:
        print("candidates.source   — OK (nothing to migrate)")
        return
    table.update({"source": "local"}, _Q.source == "llm")
    print(f"candidates.source   — migrated {len(stale)} record(s): 'llm' → 'local'")


# ------------------------------------------------------------------
# answers: backfill missing `date` field from `timestamp`
# ------------------------------------------------------------------

def _migrate_answers_date(db: TinyDB) -> None:
    table = db.table("answers")
    missing = [r for r in table.all() if not r.get("date")]
    if not missing:
        print("answers.date        — OK (nothing to migrate)")
        return
    fixed = 0
    for record in missing:
        ts = record.get("timestamp", "")
        date = ts[:10] if len(ts) >= 10 else "1970-01-01"
        table.update({"date": date}, doc_ids=[record.doc_id])
        fixed += 1
    print(f"answers.date        — backfilled {fixed} record(s) from timestamp")


# ------------------------------------------------------------------
# custom_questions: ensure all optional fields exist
# ------------------------------------------------------------------

CUSTOM_Q_DEFAULTS = {
    "explanation": "",
    "opts": [],
    "hint": "",
    "passage_id": "",
}


def _migrate_custom_questions_fields(db: TinyDB) -> None:
    table = db.table("custom_questions")
    fixed = 0
    for record in table.all():
        patch = {k: v for k, v in CUSTOM_Q_DEFAULTS.items() if k not in record}
        if patch:
            table.update(patch, doc_ids=[record.doc_id])
            fixed += 1
    if fixed:
        print(f"custom_questions    — patched {fixed} record(s) with missing default fields")
    else:
        print("custom_questions    — OK (nothing to migrate)")


# ------------------------------------------------------------------

if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        sys.exit(1)

    print(f"Migrating {DB_PATH}\n")
    with TinyDB(DB_PATH, indent=2, ensure_ascii=False) as db:
        migrate(db)
    print("\nDone.")
