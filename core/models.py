from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Question:
    id: str
    cat: str
    type: str          # 'mc', 'fill', 'reading'
    difficulty: str
    q: str
    answer: int | str  # index (int) for mc/reading, text (str) for fill
    explanation: str = ""
    opts: list[str] = field(default_factory=list)
    hint: str = ""
    passage_id: str = ""

    def correct_answer_text(self) -> str:
        if self.type in ("mc", "reading") and self.opts:
            return self.opts[int(self.answer)]
        return str(self.answer)

    def check_answer(self, user_answer: str) -> bool:
        if self.type in ("mc", "reading"):
            try:
                return int(user_answer) == int(self.answer)
            except ValueError:
                return user_answer.strip().lower() == self.opts[int(self.answer)].strip().lower()
        return user_answer.strip().lower() == str(self.answer).strip().lower()


@dataclass
class AnswerRecord:
    user_id: int
    question_id: str
    user_answer: str
    correct: bool
    timestamp: str   # ISO-8601
    date: str        # YYYY-MM-DD


@dataclass
class UserStats:
    user_id: int
    total_answered: int = 0
    total_correct: int = 0
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    wrong_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class UserInfo:
    user_id: int
    chat_id: int
    first_name: str


@dataclass
class QuestionCandidate:
    id: str
    question_data: dict
    status: str = "pending"   # pending, approved, rejected
    created_at: str = ""
    source: str = "llm"
