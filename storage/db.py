"""TinyDB-backed storage.

Tables:
  answers            — user answer history
  custom_questions   — user-added + edited questions (override bank by ID)
  hidden_questions   — bank question IDs removed from the pool
  users              — registered Telegram users for daily push
  daily_assignments  — per-user per-day question assignment
  question_candidates — LLM-generated question candidates awaiting review
  learning_plans     — per-user AI-generated learning plan + theme history
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tinydb import TinyDB, Query

from core.models import AnswerRecord, Question, QuestionCandidate

_Q = Query()


class Storage:
    def __init__(self, db_path: Path, stats_backup_path: Path, questions_backup_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path, indent=2, ensure_ascii=False)
        self._stats_backup_path = stats_backup_path
        self._questions_backup_path = questions_backup_path

        self._answers = self._db.table("answers")
        self._custom_questions = self._db.table("custom_questions")
        self._hidden = self._db.table("hidden_questions")
        self._users = self._db.table("users")
        self._daily_assignments = self._db.table("daily_assignments")
        self._candidates = self._db.table("question_candidates")
        self._learning_plans = self._db.table("learning_plans")

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------

    def save_answer(self, record: AnswerRecord) -> None:
        self._answers.insert({
            "user_id": record.user_id,
            "question_id": record.question_id,
            "user_answer": record.user_answer,
            "correct": record.correct,
            "timestamp": record.timestamp,
            "date": record.date,
        })

    def get_user_answers(self, user_id: int) -> list[dict]:
        return self._answers.search(_Q.user_id == user_id)

    def get_wrong_question_ids(self, user_id: int) -> dict[str, int]:
        records = self._answers.search(
            (_Q.user_id == user_id) & (_Q.correct == False)  # noqa: E712
        )
        counts: dict[str, int] = {}
        for r in records:
            counts[r["question_id"]] = counts.get(r["question_id"], 0) + 1
        return counts

    def get_answered_question_ids(self, user_id: int) -> set[str]:
        return {r["question_id"] for r in self._answers.search(_Q.user_id == user_id)}

    def has_answered_today(self, user_id: int, question_id: str) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        return bool(self._answers.search(
            (_Q.user_id == user_id) & (_Q.question_id == question_id) & (_Q.date == today)
        ))

    def get_answers_by_date(self, user_id: int, date: str) -> list[dict]:
        return self._answers.search((_Q.user_id == user_id) & (_Q.date == date))

    # ------------------------------------------------------------------
    # Users (for daily push)
    # ------------------------------------------------------------------

    def register_user(self, user_id: int, chat_id: int, first_name: str) -> None:
        self._users.upsert(
            {"user_id": user_id, "chat_id": chat_id, "first_name": first_name},
            _Q.user_id == user_id,
        )

    def get_all_users(self) -> list[dict]:
        return self._users.all()

    # ------------------------------------------------------------------
    # Daily assignments (per-user weighted random)
    # ------------------------------------------------------------------

    def set_daily_assignment(self, user_id: int, date: str, question_id: str) -> None:
        self._daily_assignments.upsert(
            {"user_id": user_id, "date": date, "question_id": question_id},
            (_Q.user_id == user_id) & (_Q.date == date),
        )

    def get_daily_assignment(self, user_id: int, date: str) -> str | None:
        r = self._daily_assignments.get((_Q.user_id == user_id) & (_Q.date == date))
        return r["question_id"] if r else None

    # ------------------------------------------------------------------
    # Custom questions (also used for edits of bank questions)
    # ------------------------------------------------------------------

    def save_custom_question(self, question: Question) -> None:
        self._custom_questions.upsert(
            {
                "id": question.id,
                "cat": question.cat,
                "type": question.type,
                "difficulty": question.difficulty,
                "q": question.q,
                "answer": question.answer,
                "explanation": question.explanation,
                "opts": question.opts,
                "hint": question.hint,
                "passage_id": question.passage_id,
            },
            _Q.id == question.id,
        )

    def delete_custom_question(self, question_id: str) -> None:
        self._custom_questions.remove(_Q.id == question_id)

    def get_custom_questions(self) -> list[dict]:
        return self._custom_questions.all()

    def is_custom_question(self, question_id: str) -> bool:
        return bool(self._custom_questions.get(_Q.id == question_id))

    # ------------------------------------------------------------------
    # Hidden questions (bank questions removed from pool)
    # ------------------------------------------------------------------

    def hide_question(self, question_id: str) -> None:
        if not self._hidden.get(_Q.question_id == question_id):
            self._hidden.insert({"question_id": question_id})

    def get_hidden_question_ids(self) -> set[str]:
        return {r["question_id"] for r in self._hidden.all()}

    # ------------------------------------------------------------------
    # Question candidates (LLM-generated)
    # ------------------------------------------------------------------

    def save_candidate(self, candidate: QuestionCandidate) -> None:
        self._candidates.insert({
            "id": candidate.id,
            "question_data": candidate.question_data,
            "status": candidate.status,
            "created_at": candidate.created_at,
            "source": candidate.source,
        })

    def get_candidates(self, status: str = "pending") -> list[dict]:
        return self._candidates.search(_Q.status == status)

    def get_candidate(self, candidate_id: str) -> dict | None:
        return self._candidates.get(_Q.id == candidate_id)

    def update_candidate(self, candidate_id: str, **kwargs) -> None:
        self._candidates.update(kwargs, _Q.id == candidate_id)

    # ------------------------------------------------------------------
    # Learning plans
    # ------------------------------------------------------------------

    def get_learning_plan(self, user_id: int) -> dict | None:
        return self._learning_plans.get(_Q.user_id == user_id)

    def save_learning_plan(self, user_id: int, plan: dict) -> None:
        self._learning_plans.upsert({"user_id": user_id, **plan}, _Q.user_id == user_id)

    def update_learning_plan(self, user_id: int, **kwargs) -> None:
        if self._learning_plans.get(_Q.user_id == user_id):
            self._learning_plans.update(kwargs, _Q.user_id == user_id)
        else:
            self._learning_plans.insert({"user_id": user_id, **kwargs})

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def backup(self) -> tuple[Path, Path]:
        with open(self._stats_backup_path, "w", encoding="utf-8") as f:
            json.dump(self._answers.all(), f, indent=2, ensure_ascii=False)
        with open(self._questions_backup_path, "w", encoding="utf-8") as f:
            json.dump(self._custom_questions.all(), f, indent=2, ensure_ascii=False)
        return self._stats_backup_path, self._questions_backup_path
