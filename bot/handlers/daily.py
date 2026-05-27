"""Handler for the /daily command — per-user weighted daily question."""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatting import escape, passage_block, question_header, result_text
from bot.keyboards import mc_keyboard, next_question_keyboard
from core.engine import LearningEngine
from core.models import Question

logger = logging.getLogger(__name__)
DAILY_Q_KEY = "daily_question"


async def daily_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user = update.effective_user
    engine.register_user(user.id, user.id, user.first_name or "")
    msg = update.effective_message

    if engine.has_answered_daily(user.id):
        q = engine.assign_daily_question(user.id)
        await msg.reply_text(
            f"✅ Already answered today's question.\n"
            f"Come back tomorrow for a new one!\n\n"
            f"Today's: <i>{escape(q.q)}</i>",
            parse_mode="HTML",
            reply_markup=next_question_keyboard("menu_learn"),
        )
        return

    q = engine.assign_daily_question(user.id)
    ctx.user_data[DAILY_Q_KEY] = q.id
    await _send_question(msg, q, engine, prefix="📅 <b>Daily Question</b>\n\n")


async def daily_answer_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id

    # Prefer user_data (command flow); fall back to DB (push flow)
    question_id = ctx.user_data.get(DAILY_Q_KEY)
    if not question_id:
        question_id = engine.get_daily_assigned_question_id(user_id)
    if not question_id:
        await query.edit_message_text("No daily question found. Use /daily to get one.")
        return

    q = engine.bank.get(question_id)
    if not q:
        await query.edit_message_text("Question not found. Use /daily to start again.")
        return

    raw_answer = query.data.split("_", 1)[1]  # "daily_2" → "2"
    result = engine.submit_answer(user_id, q, raw_answer)

    await query.edit_message_text(
        result_text(result.correct, result.correct_answer, result.explanation),
        parse_mode="HTML",
        reply_markup=next_question_keyboard("menu_learn"),
    )


async def _send_question(message, q: Question, engine: LearningEngine, prefix: str = "") -> None:
    logger.info("Daily: sending question %s type=%s opts=%d", q.id, q.type, len(q.opts))
    header = question_header(q, mode_prefix=prefix)

    if q.type == "reading" and q.passage_id:
        header = prefix + passage_block(engine.bank.get_passage(q.passage_id)) + question_header(q)

    if q.type == "fill":
        hint = f"\n💡 <i>{escape(q.hint)}</i>" if q.hint else ""
        await message.reply_text(
            header + hint + "\n\n✏️ Type your answer:",
            parse_mode="HTML",
        )
    else:
        await message.reply_text(
            header,
            parse_mode="HTML",
            reply_markup=mc_keyboard(q, prefix="daily"),
        )


async def send_daily_push(bot, chat_id: int, user_id: int, engine: LearningEngine) -> None:
    """Called by the 9am job to proactively push the daily question."""
    if engine.has_answered_daily(user_id):
        return
    q = engine.assign_daily_question(user_id)
    logger.info("Daily push → user %s question %s type=%s", user_id, q.id, q.type)
    header = question_header(q, mode_prefix="📅 <b>Daily Question</b>\n\n")

    if q.type == "reading" and q.passage_id:
        header = (
            "📅 <b>Daily Question</b>\n\n"
            + passage_block(engine.bank.get_passage(q.passage_id))
            + question_header(q)
        )

    if q.type == "fill":
        hint = f"\n💡 <i>{escape(q.hint)}</i>" if q.hint else ""
        await bot.send_message(
            chat_id=chat_id,
            text=header + hint + "\n\n✏️ Type your answer:",
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=header,
            parse_mode="HTML",
            reply_markup=mc_keyboard(q, prefix="daily"),
        )
