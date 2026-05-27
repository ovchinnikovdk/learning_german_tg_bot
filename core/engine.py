"""LearningEngine — single source of truth for business logic.

No Telegram imports here. Can be driven by any interface (CLI, web, bot, etc.).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from core.models import AnswerRecord, Question, QuestionCandidate, UserInfo, UserStats
from core.question_bank import QuestionBank
from storage.db import Storage


@dataclass
class AnswerResult:
    correct: bool
    correct_answer: str
    explanation: str
    passage: str = ""


def _validate_candidate(raw: dict) -> bool:
    required = ["type", "cat", "difficulty", "q", "answer"]
    if not all(k in raw for k in required):
        return False
    if raw["type"] == "mc":
        opts = raw.get("opts", [])
        if len(opts) < 2:
            return False
        try:
            ans = int(raw["answer"])
            if ans < 0 or ans >= len(opts):
                return False
        except (ValueError, TypeError):
            return False
    return bool(raw.get("q", "").strip())


class LearningEngine:
    def __init__(self, bank: QuestionBank, storage: Storage) -> None:
        self.bank = bank
        self.storage = storage
        self._last_question_id: dict[int, str] = {}

    # ------------------------------------------------------------------
    # User registration (for daily push)
    # ------------------------------------------------------------------

    def register_user(self, user_id: int, chat_id: int, first_name: str) -> None:
        self.storage.register_user(user_id, chat_id, first_name)

    def get_all_users(self) -> list[UserInfo]:
        return [
            UserInfo(user_id=r["user_id"], chat_id=r["chat_id"], first_name=r["first_name"])
            for r in self.storage.get_all_users()
        ]

    # ------------------------------------------------------------------
    # Daily question — per-user weighted random
    # ------------------------------------------------------------------

    def assign_daily_question(self, user_id: int) -> Question:
        """Return today's question for this user, creating assignment if needed."""
        today = datetime.now().strftime("%Y-%m-%d")
        existing_id = self.storage.get_daily_assignment(user_id, today)
        if existing_id:
            q = self.bank.get(existing_id)
            if q:
                return q
        wrong = self.storage.get_wrong_question_ids(user_id)
        answered = self.storage.get_answered_question_ids(user_id)
        q = self.bank.pick_for_learn(wrong, answered, exclude_id=None)
        self.storage.set_daily_assignment(user_id, today, q.id)
        return q

    def has_answered_daily(self, user_id: int) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        question_id = self.storage.get_daily_assignment(user_id, today)
        if not question_id:
            return False
        return self.storage.has_answered_today(user_id, question_id)

    def get_daily_assigned_question_id(self, user_id: int) -> str | None:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.storage.get_daily_assignment(user_id, today)

    # ------------------------------------------------------------------
    # Learn mode
    # ------------------------------------------------------------------

    def get_learn_question(self, user_id: int) -> Question:
        wrong = self.storage.get_wrong_question_ids(user_id)
        answered = self.storage.get_answered_question_ids(user_id)
        last = self._last_question_id.get(user_id)
        q = self.bank.pick_for_learn(wrong, answered, exclude_id=last)
        self._last_question_id[user_id] = q.id
        return q

    # ------------------------------------------------------------------
    # Submitting an answer
    # ------------------------------------------------------------------

    def submit_answer(self, user_id: int, question: Question, user_answer: str) -> AnswerResult:
        correct = question.check_answer(user_answer)
        now = datetime.now()
        record = AnswerRecord(
            user_id=user_id,
            question_id=question.id,
            user_answer=user_answer,
            correct=correct,
            timestamp=now.isoformat(),
            date=now.strftime("%Y-%m-%d"),
        )
        self.storage.save_answer(record)
        passage = ""
        if question.type == "reading" and question.passage_id:
            passage = self.bank.get_passage(question.passage_id)
        return AnswerResult(
            correct=correct,
            correct_answer=question.correct_answer_text(),
            explanation=question.explanation,
            passage=passage,
        )

    # ------------------------------------------------------------------
    # Stats & weak spots
    # ------------------------------------------------------------------

    def get_stats(self, user_id: int) -> UserStats:
        records = self.storage.get_user_answers(user_id)
        stats = UserStats(user_id=user_id)
        stats.total_answered = len(records)
        stats.total_correct = sum(1 for r in records if r["correct"])
        for r in records:
            q = self.bank.get(r["question_id"])
            cat = q.cat if q else "unknown"
            c, t = stats.by_category.get(cat, (0, 0))
            stats.by_category[cat] = (c + (1 if r["correct"] else 0), t + 1)
            if not r["correct"]:
                stats.wrong_counts[r["question_id"]] = (
                    stats.wrong_counts.get(r["question_id"], 0) + 1
                )
        return stats

    def get_weak_spots(self, user_id: int, top_n: int = 5) -> list[tuple[Question, int]]:
        wrong = self.storage.get_wrong_question_ids(user_id)
        ranked = sorted(wrong.items(), key=lambda x: x[1], reverse=True)[:top_n]
        result = []
        for qid, count in ranked:
            q = self.bank.get(qid)
            if q:
                result.append((q, count))
        return result

    # ------------------------------------------------------------------
    # Add / edit / delete questions
    # ------------------------------------------------------------------

    def add_custom_question(self, question: Question) -> None:
        self.bank.add_question(question)
        self.storage.save_custom_question(question)

    def edit_question(self, question: Question) -> None:
        """Edit any question (bank or custom) — persists to custom_questions table."""
        self.bank.add_question(question)
        self.storage.save_custom_question(question)

    def delete_question(self, question_id: str) -> None:
        if self.storage.is_custom_question(question_id):
            self.storage.delete_custom_question(question_id)
        else:
            self.storage.hide_question(question_id)
        self.bank.remove_question(question_id)

    # ------------------------------------------------------------------
    # Question candidates (LLM-generated)
    # ------------------------------------------------------------------

    def get_pending_candidates(self) -> list[dict]:
        return self.storage.get_candidates(status="pending")

    def approve_candidate(self, candidate_id: str) -> Question | None:
        raw = self.storage.get_candidate(candidate_id)
        if not raw:
            return None
        d = raw["question_data"]
        q = Question(
            id=f"gen_{uuid.uuid4().hex[:8]}",
            cat=d.get("cat", "general"),
            type=d.get("type", "mc"),
            difficulty=d.get("difficulty", "A2"),
            q=d.get("q", ""),
            answer=d.get("answer", 0),
            explanation=d.get("explanation", ""),
            opts=d.get("opts", []),
            hint=d.get("hint", ""),
        )
        self.add_custom_question(q)
        self.storage.update_candidate(candidate_id, status="approved")
        return q

    def reject_candidate(self, candidate_id: str) -> None:
        self.storage.update_candidate(candidate_id, status="rejected")

    def update_candidate_data(self, candidate_id: str, question_data: dict) -> None:
        self.storage.update_candidate(candidate_id, question_data=question_data)

    async def generate_candidates(self, user_id: int) -> list[QuestionCandidate]:
        """Call LLM to generate new question candidates based on user performance."""
        import random as _random
        from core.llm import build_generation_prompt, generate_questions
        from config import settings

        stats = self.get_stats(user_id)
        pct = (
            round(100 * stats.total_correct / stats.total_answered)
            if stats.total_answered > 0
            else 0
        )
        weak_cats = [
            cat
            for cat, (correct, total) in stats.by_category.items()
            if total > 0 and correct / total < 0.6
        ]

        all_answers = self.storage.get_user_answers(user_id)

        # A question is "learned" once the student has answered it correctly 4+ times
        correct_counts: dict[str, int] = {}
        for r in all_answers:
            if r["correct"]:
                correct_counts[r["question_id"]] = correct_counts.get(r["question_id"], 0) + 1

        recent_wrong = [
            r for r in sorted(all_answers, key=lambda x: x.get("timestamp", ""), reverse=True)
            if not r["correct"] and correct_counts.get(r["question_id"], 0) < 4
        ][:5]
        mistakes = []
        for r in recent_wrong:
            q = self.bank.get(r["question_id"])
            if q:
                mistakes.append({"q": q.q, "cat": q.cat, "difficulty": q.difficulty})

        # --- Good examples: 3 real mc questions, weighted toward user's weak spots ---
        # Build a weighted pool: wrong_count+1 for each question the user got wrong,
        # 1 for everything else. Sample 3 without replacement.
        all_mc = [q for qid in self.bank.all_ids()
                  if (q := self.bank.get(qid)) and q.type == "mc" and q.opts]
        wrong_counts = stats.wrong_counts  # {question_id: wrong_count}
        pool_ids = [q.id for q in all_mc]
        pool_weights = [wrong_counts.get(q.id, 0) + 1 for q in all_mc]
        # Boost questions from weak categories an extra 2×
        weak_set = set(weak_cats)
        pool_weights = [
            w * 3 if all_mc[i].cat in weak_set else w
            for i, w in enumerate(pool_weights)
        ]
        # Weighted sample without replacement (3 items)
        chosen_ids: list[str] = []
        remaining_ids = pool_ids[:]
        remaining_w = pool_weights[:]
        for _ in range(min(3, len(remaining_ids))):
            total = sum(remaining_w)
            pick = _random.choices(remaining_ids, weights=remaining_w, k=1)[0]
            idx = remaining_ids.index(pick)
            chosen_ids.append(pick)
            remaining_ids.pop(idx)
            remaining_w.pop(idx)

        example_dicts = [
            {
                "type": q.type,
                "cat": q.cat,
                "difficulty": q.difficulty,
                "q": q.q,
                "opts": q.opts,
                "answer": int(q.answer),
                "explanation": q.explanation,
            }
            for qid in chosen_ids
            if (q := self.bank.get(qid))
        ]

        # --- Bad example: most recently rejected candidate (1 item) ---
        rejected_raw = self.storage.get_candidates(status="rejected")
        rejected_dicts = [rejected_raw[-1]["question_data"]] if rejected_raw else []

        prompt = build_generation_prompt(
            stats_pct=pct,
            weak_cats=weak_cats,
            recent_mistakes=mistakes,
            available_cats=self.bank.categories(),
            example_questions=example_dicts,
            rejected_questions=rejected_dicts,
            total_answered=stats.total_answered,
            total_correct=stats.total_correct,
            by_category=stats.by_category,
        )

        raw_questions, llm_source = await generate_questions(
            prompt,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
            anthropic_api_key=settings.anthropic_api_key,
            anthropic_model=settings.anthropic_model,
        )

        # Collect all existing question texts (pending + rejected) to deduplicate
        existing_texts = {
            r["question_data"].get("q", "").strip().lower()
            for r in (
                self.storage.get_candidates(status="pending")
                + self.storage.get_candidates(status="rejected")
            )
        }

        candidates = []
        for raw in raw_questions:
            if not _validate_candidate(raw):
                continue
            if raw.get("q", "").strip().lower() in existing_texts:
                continue  # skip duplicate / re-generated rejected question
            cid = f"cand_{uuid.uuid4().hex[:8]}"
            candidate = QuestionCandidate(
                id=cid,
                question_data=raw,
                status="pending",
                created_at=datetime.now().isoformat(),
                source=llm_source,
            )
            self.storage.save_candidate(candidate)
            existing_texts.add(raw["q"].strip().lower())  # prevent intra-batch dups
            candidates.append(candidate)

        return candidates

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def backup(self) -> tuple[str, str]:
        stats_path, questions_path = self.storage.backup()
        return str(stats_path), str(questions_path)
