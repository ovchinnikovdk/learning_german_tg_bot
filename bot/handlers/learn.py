"""Handler for /learn — adaptive question practice."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

import logging

from bot.formatting import escape, passage_block, question_header, result_text
from bot.keyboards import fill_question_keyboard, mc_keyboard, next_question_keyboard
from core.engine import LearningEngine
from core.models import Question

logger = logging.getLogger(__name__)

LEARN_Q_KEY = "learn_question"
TOPIC_IDS_KEY = "topic_practice_ids"


async def learn_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id
    ctx.user_data.pop(TOPIC_IDS_KEY, None)  # exit topic mode on /learn
    q = engine.get_learn_question(user_id)
    ctx.user_data[LEARN_Q_KEY] = q.id
    await _send_question(update.effective_message, q, engine)


async def learn_next_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id

    topic_ids = ctx.user_data.get(TOPIC_IDS_KEY)
    if topic_ids:
        q = engine.get_topic_learn_question(user_id, topic_ids)
        if q:
            ctx.user_data[LEARN_Q_KEY] = q.id
            await _send_question(query.message, q, engine, mode_prefix="📚 <b>Topic Practice</b>\n\n")
            return
        # Topic pool exhausted — fall through to normal learn
        ctx.user_data.pop(TOPIC_IDS_KEY, None)
        await query.message.reply_text("✅ All topic exercises done! Continuing with general practice.")

    q = engine.get_learn_question(user_id)
    ctx.user_data[LEARN_Q_KEY] = q.id
    await _send_question(query.message, q, engine)


async def learn_mc_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id

    question_id = ctx.user_data.get(LEARN_Q_KEY)
    if not question_id:
        await query.edit_message_text("Session expired. Use /learn to start.")
        return

    q = engine.bank.get(question_id)
    raw_answer = query.data.split("_", 1)[1]  # "learn_2" → "2"
    result = engine.submit_answer(user_id, q, raw_answer)

    await query.edit_message_text(
        result_text(result.correct, result.correct_answer, result.explanation),
        parse_mode="HTML",
        reply_markup=next_question_keyboard("learn_next", question_id=question_id),
    )


async def learn_fill_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle typed answers for fill-in-the-blank questions."""
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id

    question_id = ctx.user_data.get(LEARN_Q_KEY)
    if not question_id:
        return

    q = engine.bank.get(question_id)
    if not q or q.type != "fill":
        return

    result = engine.submit_answer(user_id, q, update.message.text.strip())
    ctx.user_data.pop(LEARN_Q_KEY, None)
    await update.message.reply_text(
        result_text(result.correct, result.correct_answer, result.explanation),
        parse_mode="HTML",
        reply_markup=next_question_keyboard("learn_next", question_id=question_id),
    )


async def _send_question(
    message,
    q: Question,
    engine: LearningEngine,
    mode_prefix: str = "🎓 <b>Learn Mode</b>\n\n",
) -> None:
    logger.info("Sending question %s type=%s opts=%d", q.id, q.type, len(q.opts))
    header = question_header(q, mode_prefix=mode_prefix)

    if q.type == "reading" and q.passage_id:
        header = prefix + passage_block(engine.bank.get_passage(q.passage_id)) + \
                 question_header(q)

    if q.type == "fill":
        hint = f"\n💡 <i>{escape(q.hint)}</i>" if q.hint else ""
        await message.reply_text(
            header + hint + "\n\n✏️ Type your answer:",
            parse_mode="HTML",
            reply_markup=fill_question_keyboard(q.id),
        )
    else:
        await message.reply_text(
            header,
            parse_mode="HTML",
            reply_markup=mc_keyboard(q, prefix="learn", question_id=q.id),
        )
