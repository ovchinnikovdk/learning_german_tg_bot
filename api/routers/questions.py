from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import AddQuestionIn, AddQuestionOut, QuestionOut
from core.engine import LearningEngine
from core.models import Question

router = APIRouter(prefix="/questions", tags=["questions"])


def _engine(request: Request) -> LearningEngine:
    return request.app.state.engine


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, engine: LearningEngine = Depends(_engine)):
    q = engine.bank.get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    passage = ""
    if q.type == "reading" and q.passage_id:
        passage = engine.bank.get_passage(q.passage_id)
    return QuestionOut(
        id=q.id, cat=q.cat, type=q.type, difficulty=q.difficulty,
        q=q.q, opts=q.opts, hint=q.hint, passage=passage,
    )


@router.post("", response_model=AddQuestionOut, status_code=201)
def add_question(body: AddQuestionIn, engine: LearningEngine = Depends(_engine)):
    q = Question(
        id=f"custom_{uuid.uuid4().hex[:8]}",
        cat=body.cat,
        type=body.type,
        difficulty=body.difficulty,
        q=body.q,
        answer=body.answer,
        explanation=body.explanation,
        opts=body.opts,
        hint=body.hint,
    )
    engine.add_custom_question(q)
    return AddQuestionOut(id=q.id, message="Question added successfully.")
