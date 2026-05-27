"""Multi-step ConversationHandler for adding a custom question to the bank."""
from __future__ import annotations

import uuid

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.formatting import escape
from bot.keyboards import (
    category_keyboard,
    difficulty_keyboard,
    question_type_keyboard,
    confirm_keyboard,
)
from core.engine import LearningEngine
from core.models import Question

# Conversation states
(
    CHOOSE_TYPE,
    CHOOSE_CATEGORY,
    CHOOSE_DIFFICULTY,
    ENTER_QUESTION,
    ENTER_OPTIONS,
    ENTER_ANSWER,
    ENTER_EXPLANATION,
    CONFIRM,
) = range(8)

_DATA = "add_q_data"


async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[_DATA] = {}
    await update.message.reply_text(
        "➕ *Add a new question*\n\nSelect question type:",
        parse_mode="Markdown",
        reply_markup=question_type_keyboard(),
    )
    return CHOOSE_TYPE


async def choose_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    q_type = query.data.split("_", 1)[1]  # type_mc -> mc
    ctx.user_data[_DATA]["type"] = q_type

    engine: LearningEngine = ctx.bot_data["engine"]
    await query.edit_message_text(
        "Select category:",
        reply_markup=category_keyboard(engine.bank.categories()),
    )
    return CHOOSE_CATEGORY


async def choose_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cat = query.data[4:]  # cat_grammar_articles -> grammar_articles
    ctx.user_data[_DATA]["cat"] = cat

    await query.edit_message_text(
        "Select difficulty level:",
        reply_markup=difficulty_keyboard(),
    )
    return CHOOSE_DIFFICULTY


async def choose_difficulty(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    diff = query.data.split("_", 1)[1]  # diff_A1 -> A1
    ctx.user_data[_DATA]["difficulty"] = diff

    await query.edit_message_text("Type the question text:")
    return ENTER_QUESTION


async def enter_question(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[_DATA]["q"] = update.message.text.strip()
    q_type = ctx.user_data[_DATA]["type"]

    if q_type == "mc":
        await update.message.reply_text(
            "Enter the 4 answer options, one per line:\n\n"
            "Example:\nDer\nDie\nDas\nEin"
        )
        return ENTER_OPTIONS

    await update.message.reply_text("Type the correct answer:")
    return ENTER_ANSWER


async def enter_options(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    opts = [line.strip() for line in update.message.text.strip().splitlines() if line.strip()]
    if len(opts) < 2:
        await update.message.reply_text("Please enter at least 2 options, one per line:")
        return ENTER_OPTIONS

    ctx.user_data[_DATA]["opts"] = opts
    options_display = "\n".join(f"{chr(65+i)}. {o}" for i, o in enumerate(opts))
    await update.message.reply_text(
        f"Options:\n{options_display}\n\nEnter the *letter* of the correct answer (A, B, C…):",
        parse_mode="Markdown",
    )
    return ENTER_ANSWER


async def enter_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    data = ctx.user_data[_DATA]

    if data["type"] == "mc":
        letter = raw.upper()
        if letter not in "ABCD" or ord(letter) - 65 >= len(data.get("opts", [])):
            await update.message.reply_text("Please enter a valid letter (A, B, C…):")
            return ENTER_ANSWER
        data["answer"] = ord(letter) - 65  # store as index
    else:
        data["answer"] = raw

    await update.message.reply_text("Add an explanation (or send /skip to leave it blank):")
    return ENTER_EXPLANATION


async def enter_explanation(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[_DATA]["explanation"] = update.message.text.strip()
    return await _show_preview(update, ctx)


async def skip_explanation(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[_DATA]["explanation"] = ""
    return await _show_preview(update, ctx)


async def _show_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    d = ctx.user_data[_DATA]
    opts_text = ""
    if d.get("opts"):
        opts_text = "\n" + "\n".join(f"  {chr(65+i)}. {o}" for i, o in enumerate(d["opts"]))

    preview = (
        f"📋 <b>Preview</b>\n\n"
        f"<b>Type:</b> {escape(d['type'])}\n"
        f"<b>Category:</b> {escape(d['cat'])}\n"
        f"<b>Difficulty:</b> {escape(d['difficulty'])}\n"
        f"<b>Question:</b> {escape(d['q'])}{escape(opts_text)}\n"
        f"<b>Answer:</b> {escape(str(d['answer']))}\n"
        f"<b>Explanation:</b> {escape(d.get('explanation') or '—')}\n\n"
        f"Save this question?"
    )
    await update.message.reply_text(
        preview,
        parse_mode="HTML",
        reply_markup=confirm_keyboard("add_confirm_yes", "add_confirm_no"),
    )
    return CONFIRM


async def confirm_yes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    engine: LearningEngine = ctx.bot_data["engine"]
    d = ctx.user_data[_DATA]
    q = Question(
        id=f"custom_{uuid.uuid4().hex[:8]}",
        cat=d["cat"],
        type=d["type"],
        difficulty=d["difficulty"],
        q=d["q"],
        answer=d["answer"],
        explanation=d.get("explanation", ""),
        opts=d.get("opts", []),
    )
    engine.add_custom_question(q)

    await query.edit_message_text("✅ Question saved! Use /learn to practice it.")
    ctx.user_data.pop(_DATA, None)
    return ConversationHandler.END


async def confirm_no(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled. No question was saved.")
    ctx.user_data.pop(_DATA, None)
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    ctx.user_data.pop(_DATA, None)
    return ConversationHandler.END


def build_add_question_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            CHOOSE_TYPE: [CallbackQueryHandler(choose_type, pattern="^type_")],
            CHOOSE_CATEGORY: [CallbackQueryHandler(choose_category, pattern="^cat_")],
            CHOOSE_DIFFICULTY: [CallbackQueryHandler(choose_difficulty, pattern="^diff_")],
            ENTER_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_question)],
            ENTER_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_options)],
            ENTER_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_answer)],
            ENTER_EXPLANATION: [
                CommandHandler("skip", skip_explanation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_explanation),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_yes, pattern="^add_confirm_yes$"),
                CallbackQueryHandler(confirm_no, pattern="^add_confirm_no$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
