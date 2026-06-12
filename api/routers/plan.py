from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import LearningPlanOut, TopicOut
from core.engine import LearningEngine

router = APIRouter(prefix="/plan", tags=["plan"])


def _engine(request: Request) -> LearningEngine:
    return request.app.state.engine


def _to_topic_out(t: dict) -> TopicOut:
    return TopicOut(
        id=t.get("id", ""),
        name=t.get("name", ""),
        description=t.get("description", ""),
        grammar_rules=t.get("grammar_rules", []),
        examples=t.get("examples", []),
        focus_categories=t.get("focus_categories", []),
        started_at=t.get("started_at", ""),
        completed_at=t.get("completed_at", ""),
    )


def _to_plan_out(plan: dict) -> LearningPlanOut:
    return LearningPlanOut(
        user_id=plan["user_id"],
        ai_summary=plan.get("ai_summary", ""),
        recommended_progression=plan.get("recommended_progression", []),
        weak_areas=plan.get("weak_areas", []),
        strengths=plan.get("strengths", []),
        generated_at=plan.get("generated_at", ""),
        topics_history=[_to_topic_out(t) for t in plan.get("topics_history", [])],
        current_topic=_to_topic_out(plan["current_topic"]) if plan.get("current_topic") else None,
    )


@router.get("/{user_id}", response_model=LearningPlanOut)
def get_plan(user_id: int, engine: LearningEngine = Depends(_engine)):
    plan = engine.get_learning_plan(user_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No learning plan found for this user")
    return _to_plan_out(plan)


@router.post("/{user_id}/generate", response_model=LearningPlanOut)
async def generate_plan(user_id: int, engine: LearningEngine = Depends(_engine)):
    plan = await engine.generate_learning_plan(user_id)
    return _to_plan_out(plan)


@router.post("/{user_id}/topic", response_model=TopicOut)
async def generate_topic(user_id: int, engine: LearningEngine = Depends(_engine)):
    existing = engine.get_learning_plan(user_id)
    if existing and existing.get("current_topic"):
        raise HTTPException(status_code=409, detail="User already has an active topic")
    topic = await engine.generate_current_topic(user_id)
    return _to_topic_out(topic)


@router.post("/{user_id}/complete-topic", response_model=LearningPlanOut)
def complete_topic(user_id: int, engine: LearningEngine = Depends(_engine)):
    engine.complete_current_topic(user_id)
    plan = engine.get_learning_plan(user_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No learning plan found")
    return _to_plan_out(plan)
