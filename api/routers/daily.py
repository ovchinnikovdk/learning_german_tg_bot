from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.schemas import AnswerIn, AnswerResultOut, DailyStatusOut, QuestionOut
from core.engine import LearningEngine

router = APIRouter(prefix="/daily", tags=["daily"])


def _engine(request: Request) -> LearningEngine:
    return request.app.state.engine


def _question_out(q, engine: LearningEngine) -> QuestionOut:
    passage = ""
    if q.type == "reading" and q.passage_id:
        passage = engine.bank.get_passage(q.passage_id)
    return QuestionOut(
        id=q.id, cat=q.cat, type=q.type, difficulty=q.difficulty,
        q=q.q, opts=q.opts, hint=q.hint, passage=passage,
    )


@router.get("", response_model=DailyStatusOut)
def get_daily(user_id: int, engine: LearningEngine = Depends(_engine)):
    if engine.has_answered_daily(user_id):
        q = engine.get_daily_question()
        return DailyStatusOut(
            already_answered=True,
            message="Already answered today. Come back tomorrow!",
            question=_question_out(q, engine),
        )
    q = engine.get_daily_question()
    return DailyStatusOut(already_answered=False, question=_question_out(q, engine))


@router.post("/answer", response_model=AnswerResultOut)
def post_daily_answer(body: AnswerIn, engine: LearningEngine = Depends(_engine)):
    q = engine.bank.get(body.question_id)
    result = engine.submit_answer(body.user_id, q, body.answer)
    return AnswerResultOut(
        correct=result.correct,
        correct_answer=result.correct_answer,
        explanation=result.explanation,
    )
