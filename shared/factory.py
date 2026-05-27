"""Wires QuestionBank + Storage → LearningEngine.

Both the Telegram bot and the HTTP API call build_engine() so they
share the same configuration and storage files.
"""
from __future__ import annotations

from core.engine import LearningEngine
from core.models import Question
from core.question_bank import QuestionBank
from config import settings
from storage.db import Storage


def build_engine() -> LearningEngine:
    bank = QuestionBank(settings.question_bank_path)
    storage = Storage(
        settings.db_path,
        settings.stats_backup_path,
        settings.questions_backup_path,
    )

    # Apply custom questions (also acts as overrides for edited bank questions)
    for raw in storage.get_custom_questions():
        bank.add_question(Question(
            id=raw["id"], cat=raw["cat"], type=raw["type"],
            difficulty=raw["difficulty"], q=raw["q"], answer=raw["answer"],
            explanation=raw.get("explanation", ""), opts=raw.get("opts", []),
            hint=raw.get("hint", ""), passage_id=raw.get("passage_id", ""),
        ))

    # Remove any hidden (deleted) questions
    for qid in storage.get_hidden_question_ids():
        bank.remove_question(qid)

    return LearningEngine(bank, storage)
