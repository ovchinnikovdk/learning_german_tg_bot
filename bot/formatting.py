"""HTML formatting helpers for Telegram messages.

We use HTML instead of MarkdownV1 because question texts contain underscores
(e.g. '___ Mädchen') that Telegram misinterprets as italic markers.
"""
from __future__ import annotations

import html

from core.models import Question


def escape(text: str) -> str:
    return html.escape(str(text))


def question_header(q: Question, mode_prefix: str = "") -> str:
    tag = f"[{escape(q.difficulty)} | {escape(q.cat)}]"
    return f"{mode_prefix}<b>{tag}</b>\n{escape(q.q)}"


def passage_block(text: str) -> str:
    return f"📖 <b>Text:</b>\n<i>{escape(text)}</i>\n\n"


def result_text(correct: bool, correct_answer: str, explanation: str) -> str:
    emoji = "✅" if correct else "❌"
    outcome = "Correct!" if correct else "Wrong."
    lines = [
        f"{emoji} {outcome}",
        f"<b>Answer:</b> {escape(correct_answer)}",
    ]
    if explanation:
        lines.append(f"<i>{escape(explanation)}</i>")
    return "\n\n".join(lines)
