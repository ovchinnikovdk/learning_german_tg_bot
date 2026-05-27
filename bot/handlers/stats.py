"""Handler for /stats — show progress and weak spots."""
from __future__ import annotations

import io
import json
from collections import defaultdict
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.formatting import escape
from bot.keyboards import main_menu_keyboard
from core.engine import LearningEngine


def _stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download full stats (JSON)", callback_data="stats_dl")],
        [InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")],
    ])


async def stats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id
    stats = engine.get_stats(user_id)
    msg = update.effective_message

    if stats.total_answered == 0:
        await msg.reply_text(
            "No answers recorded yet. Use /daily or /learn to get started!",
            reply_markup=main_menu_keyboard(),
        )
        return

    pct = round(100 * stats.total_correct / stats.total_answered)
    wrong_total = stats.total_answered - stats.total_correct

    if pct >= 80:
        level = "🏆 Excellent"
    elif pct >= 65:
        level = "📈 Good progress"
    elif pct >= 45:
        level = "📚 Keep going"
    else:
        level = "💪 Keep practicing"

    lines = [
        f"📊 <b>Your Stats</b>  —  {level}\n",
        f"📬 {stats.total_answered} answered",
        f"✅ {stats.total_correct} correct  ({pct}%)",
        f"❌ {wrong_total} wrong",
        f"{_bar(pct)}  <b>{pct}%</b>",
    ]

    bank_counts = engine.bank.count_by_category()
    sorted_cats = sorted(
        stats.by_category.items(),
        key=lambda x: x[1][0] / x[1][1] if x[1][1] else 0,
    )

    if sorted_cats:
        lines.append("\n<b>By category</b>  (worst → best)")
        lines.append("<i>█ correct  ▓ wrong  ░ not tried</i>")
        for cat, (correct, total_ans) in sorted_cats:
            cat_pct = round(100 * correct / total_ans)
            bank_total = bank_counts.get(cat, 0)
            bar = _tri_bar(correct, total_ans, bank_total)
            flag = "  ⚠️" if cat_pct < 60 else ""
            lines.append(f"\n▸ <b>{escape(cat)}</b>{flag}")
            lines.append(f"  {bar}  {cat_pct}%  ({correct}/{total_ans})")

    # Per-question correct counts to detect learned questions
    q_correct: dict[str, int] = defaultdict(int)
    for r in engine.storage.get_user_answers(user_id):
        if r["correct"]:
            q_correct[r["question_id"]] += 1

    unlearned = sorted(
        [(qid, wc, q_correct[qid]) for qid, wc in stats.wrong_counts.items()
         if q_correct[qid] < 4],
        key=lambda x: (-x[1], x[2]),
    )
    learned_count = sum(1 for qid in stats.wrong_counts if q_correct[qid] >= 4)

    if unlearned:
        lines.append(f"\n<b>Needs work</b>  ({len(unlearned)} question(s))")
        for qid, wrong_count, corr_count in unlearned[:8]:
            q = engine.bank.get(qid)
            if q:
                snippet = escape(q.q[:45]) + ("…" if len(q.q) > 45 else "")
                lines.append(
                    f"\n❌×{wrong_count} ✅×{corr_count}  "
                    f"[{escape(q.difficulty)} · {escape(q.cat)}]"
                )
                lines.append(f"<i>{snippet}</i>")
        if len(unlearned) > 8:
            lines.append(f"\n<i>…and {len(unlearned) - 8} more</i>")

    if learned_count:
        lines.append(f"\n✅ <b>Mastered:</b> {learned_count} question(s)")

    await msg.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_stats_keyboard(),
    )


async def stats_download_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Generating…")
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id
    stats = engine.get_stats(user_id)

    pct = round(100 * stats.total_correct / stats.total_answered) if stats.total_answered else 0
    bank_counts = engine.bank.count_by_category()

    q_correct: dict[str, int] = defaultdict(int)
    q_total: dict[str, int] = defaultdict(int)
    for r in engine.storage.get_user_answers(user_id):
        q_total[r["question_id"]] += 1
        if r["correct"]:
            q_correct[r["question_id"]] += 1

    by_cat = {}
    for cat, (correct, total_ans) in stats.by_category.items():
        by_cat[cat] = {
            "correct": correct,
            "wrong": total_ans - correct,
            "total_answered": total_ans,
            "accuracy_pct": round(100 * correct / total_ans) if total_ans else 0,
            "bank_total": bank_counts.get(cat, 0),
        }

    questions = []
    for qid, total in sorted(q_total.items(), key=lambda x: -(x[1] - q_correct[x[0]])):
        q = engine.bank.get(qid)
        if not q:
            continue
        correct = q_correct[qid]
        wrong = total - correct
        questions.append({
            "question_id": qid,
            "cat": q.cat,
            "difficulty": q.difficulty,
            "type": q.type,
            "q": q.q,
            "opts": q.opts,
            "hint": q.hint,
            "times_answered": total,
            "correct_count": correct,
            "wrong_count": wrong,
            "accuracy_pct": round(100 * correct / total) if total else 0,
            "learned": correct >= 4,
        })

    payload = {
        "exported_at": datetime.now().isoformat(),
        "user_id": user_id,
        "summary": {
            "total_answered": stats.total_answered,
            "total_correct": stats.total_correct,
            "accuracy_pct": pct,
        },
        "by_category": by_cat,
        "questions": questions,
    }

    buf = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode())
    buf.name = f"stats_{user_id}.json"
    await query.message.reply_document(document=buf, filename=buf.name)


def _bar(pct: int, width: int = 8) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _tri_bar(correct: int, total_answered: int, bank_total: int, width: int = 25) -> str:
    """Three-segment bar: █ correct · ▓ answered-wrong · ░ not yet tried."""
    denom = max(bank_total, total_answered, 1)
    correct_w = round(correct / denom * width)
    answered_w = round(total_answered / denom * width)
    correct_w = min(correct_w, answered_w)
    wrong_w = answered_w - correct_w
    rest_w = width - correct_w - wrong_w
    return "█" * correct_w + "▓" * wrong_w + "░" * rest_w
