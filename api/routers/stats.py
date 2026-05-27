from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from collections import defaultdict

from api.schemas import AnsweredQuestion, StatsCategoryOut, StatsOut
from core.engine import LearningEngine

router = APIRouter(prefix="/stats", tags=["stats"])


def _engine(request: Request) -> LearningEngine:
    return request.app.state.engine


@router.get("/{user_id}", response_model=StatsOut)
def get_stats(user_id: int, engine: LearningEngine = Depends(_engine)):
    stats = engine.get_stats(user_id)
    accuracy = (
        round(100 * stats.total_correct / stats.total_answered)
        if stats.total_answered else 0
    )
    bank_counts = engine.bank.count_by_category()
    by_cat = {
        cat: StatsCategoryOut(
            correct=correct,
            wrong=total - correct,
            total_answered=total,
            accuracy_pct=round(100 * correct / total) if total else 0,
            bank_total=bank_counts.get(cat, 0),
        )
        for cat, (correct, total) in stats.by_category.items()
    }

    # Per-question counts over all answer history
    q_correct: dict[str, int] = defaultdict(int)
    q_total: dict[str, int] = defaultdict(int)
    for r in engine.storage.get_user_answers(user_id):
        q_total[r["question_id"]] += 1
        if r["correct"]:
            q_correct[r["question_id"]] += 1

    # All answered questions — sort worst-first (most wrong, then fewest correct)
    questions = []
    for qid, total in q_total.items():
        q = engine.bank.get(qid)
        if not q:
            continue
        correct = q_correct[qid]
        wrong = total - correct
        pct = round(100 * correct / total) if total else 0
        questions.append(AnsweredQuestion(
            question_id=qid,
            cat=q.cat,
            difficulty=q.difficulty,
            type=q.type,
            q=q.q,
            opts=q.opts,
            hint=q.hint,
            times_answered=total,
            correct_count=correct,
            wrong_count=wrong,
            accuracy_pct=pct,
            learned=correct >= 4,
        ))
    questions.sort(key=lambda x: (-x.wrong_count, x.correct_count))

    return StatsOut(
        total_answered=stats.total_answered,
        total_correct=stats.total_correct,
        accuracy_pct=accuracy,
        by_category=by_cat,
        questions=questions,
    )
