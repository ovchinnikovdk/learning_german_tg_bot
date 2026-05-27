"""Loads the question bank JSON and provides selection helpers."""
from __future__ import annotations

import json
import random
from pathlib import Path

from core.models import Question


class QuestionBank:
    def __init__(self, bank_path: Path) -> None:
        with open(bank_path, encoding="utf-8") as f:
            raw = json.load(f)

        self._passages: dict[str, str] = {
            p["id"]: p["text"] for p in raw.get("reading_passages", [])
        }
        self._questions: dict[str, Question] = {}
        for q in raw.get("questions", []):
            self._questions[q["id"]] = Question(
                id=q["id"],
                cat=q["cat"],
                type=q["type"],
                difficulty=q["difficulty"],
                q=q["q"],
                answer=q["answer"],
                explanation=q.get("explanation", ""),
                opts=q.get("opts", []),
                hint=q.get("hint", ""),
                passage_id=q.get("passage_id", ""),
            )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def all_ids(self) -> list[str]:
        return list(self._questions.keys())

    def get(self, question_id: str) -> Question | None:
        return self._questions.get(question_id)

    def get_passage(self, passage_id: str) -> str:
        return self._passages.get(passage_id, "")

    def add_question(self, question: Question) -> None:
        self._questions[question.id] = question

    def remove_question(self, question_id: str) -> None:
        self._questions.pop(question_id, None)

    def by_category(self, cat: str) -> list[Question]:
        return [q for q in self._questions.values() if q.cat == cat]

    def categories(self) -> list[str]:
        return sorted({q.cat for q in self._questions.values()})

    def count_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for q in self._questions.values():
            counts[q.cat] = counts.get(q.cat, 0) + 1
        return counts

    def difficulties(self) -> list[str]:
        return ["A1", "A2", "B1", "B2"]

    # ------------------------------------------------------------------
    # Selection strategy: weighted random pool
    # Used for both daily (per-user) and learn mode.
    #
    # weights = wrong_count * 3  for previously wrong answers
    #         = 1                for unanswered questions
    # Falls back to full bank if all questions have been answered correctly.
    # ------------------------------------------------------------------

    def pick_for_learn(
        self,
        wrong_counts: dict[str, int],
        answered_ids: set[str],
        exclude_id: str | None = None,
    ) -> Question:
        pool_ids: list[str] = []
        pool_weights: list[int] = []

        for qid, count in wrong_counts.items():
            if qid != exclude_id and qid in self._questions:
                pool_ids.append(qid)
                pool_weights.append(count * 3)

        for qid in self._questions:
            if qid not in answered_ids and qid != exclude_id:
                pool_ids.append(qid)
                pool_weights.append(1)

        if pool_ids:
            return self._questions[random.choices(pool_ids, weights=pool_weights, k=1)[0]]

        fallback = [qid for qid in self.all_ids() if qid != exclude_id]
        return self._questions[random.choice(fallback or self.all_ids())]
