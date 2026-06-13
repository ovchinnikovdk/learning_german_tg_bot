"""Handler for the /daily command — per-user weighted daily question."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatting import escape, result_text
from bot.keyboards import next_question_keyboard
from bot.handlers.learn import _send_question, render_question
from core.engine import LearningEngine

logger = logging.getLogger(__name__)
DAILY_Q_KEY = "daily_question"

_DAILY_PREFIX = "📅 <b>Daily Question</b>\n\n"


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
            reply_markup=next_question_keyboard("menu_learn", question_id=q.id),
        )
        return

    q = engine.assign_daily_question(user.id)
    ctx.user_data[DAILY_Q_KEY] = q.id
    await _send_question(msg, q, engine, mode_prefix=_DAILY_PREFIX, callback_prefix="daily")


async def daily_answer_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id

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
        reply_markup=next_question_keyboard("menu_learn", question_id=question_id),
    )


async def send_daily_push(bot, chat_id: int, user_id: int, engine: LearningEngine) -> None:
    """Called by the 9am job to proactively push the daily question."""
    if engine.has_answered_daily(user_id):
        return
    q = engine.assign_daily_question(user_id)
    logger.info("Daily push → user %s question %s type=%s", user_id, q.id, q.type)
    text, markup = render_question(q, engine, mode_prefix=_DAILY_PREFIX, callback_prefix="daily")
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup)
