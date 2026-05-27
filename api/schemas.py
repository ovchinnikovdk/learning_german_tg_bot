from __future__ import annotations

from pydantic import BaseModel


class QuestionOut(BaseModel):
    id: str
    cat: str
    type: str
    difficulty: str
    q: str
    opts: list[str] = []
    hint: str = ""
    passage: str = ""


class DailyStatusOut(BaseModel):
    already_answered: bool
    question: QuestionOut | None = None
    message: str = ""


class AnswerIn(BaseModel):
    user_id: int
    question_id: str
    answer: str  # option index as string for mc/reading, text for fill


class AnswerResultOut(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str


class LearnQuestionOut(BaseModel):
    question: QuestionOut


class StatsCategoryOut(BaseModel):
    correct: int
    wrong: int
    total_answered: int
    accuracy_pct: int
    bank_total: int


class AnsweredQuestion(BaseModel):
    question_id: str
    cat: str
    difficulty: str
    type: str
    q: str
    opts: list[str] = []
    hint: str = ""
    times_answered: int
    correct_count: int
    wrong_count: int
    accuracy_pct: int
    learned: bool  # correct_count >= 4


class StatsOut(BaseModel):
    total_answered: int
    total_correct: int
    accuracy_pct: int
    by_category: dict[str, StatsCategoryOut]
    questions: list[AnsweredQuestion]  # all answered questions, sorted worst-first


class AddQuestionIn(BaseModel):
    cat: str
    type: str          # 'mc' or 'fill'
    difficulty: str    # A1 / A2 / B1 / B2
    q: str
    answer: str | int  # index for mc, text for fill
    opts: list[str] = []
    explanation: str = ""
    hint: str = ""


class AddQuestionOut(BaseModel):
    id: str
    message: str


class BackupOut(BaseModel):
    stats_backup: str
    questions_backup: str


class ThemeOut(BaseModel):
    id: str
    name: str
    description: str
    grammar_rules: list[str] = []
    examples: list[dict] = []
    focus_categories: list[str] = []
    started_at: str = ""
    completed_at: str = ""


class LearningPlanOut(BaseModel):
    user_id: int
    ai_summary: str = ""
    recommended_progression: list[str] = []
    weak_areas: list[str] = []
    strengths: list[str] = []
    generated_at: str = ""
    themes_history: list[ThemeOut] = []
    current_theme: ThemeOut | None = None
