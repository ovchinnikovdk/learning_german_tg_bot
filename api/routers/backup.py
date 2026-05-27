from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.schemas import BackupOut
from core.engine import LearningEngine

router = APIRouter(prefix="/backup", tags=["backup"])


def _engine(request: Request) -> LearningEngine:
    return request.app.state.engine


@router.post("", response_model=BackupOut)
def trigger_backup(engine: LearningEngine = Depends(_engine)):
    stats_path, questions_path = engine.backup()
    return BackupOut(stats_backup=stats_path, questions_backup=questions_path)
