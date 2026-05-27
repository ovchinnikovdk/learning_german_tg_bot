"""Handlers for listing and editing questions in the bank.

Browse flow (stateless callbacks):
  ql_list          → category list
  ql_c_{cat}_{pg}  → question list for category, page pg
  ql_q_{qid}       → question detail
  ql_d_{qid}       → delete prompt
  ql_dd_{qid}      → confirm delete
  ql_noop          → page indicator (no-op)

Edit flow (ConversationHandler, entry: ql_e_{qid}):
  EDIT_SELECT_FIELD  → pick which field to change
  EDIT_SELECT_CAT    → pick new category
  EDIT_SELECT_DIFF   → pick new difficulty
  EDIT_ENTER_TEXT    → type new value
"""
from __future__ import annotations

import logging
from dataclasses import replace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    PAGE_SIZE,
    category_list_keyboard,
    edit_category_keyboard,
    edit_difficulty_keyboard,
    edit_field_keyboard,
    question_detail_keyboard,
    question_list_keyboard,
)
from core.engine import LearningEngine

logger = logging.getLogger(__name__)

EDIT_SELECT_FIELD, EDIT_SELECT_CAT, EDIT_SELECT_DIFF, EDIT_ENTER_TEXT = range(4)

_EDIT_Q_KEY = "edit_qid"
_EDIT_FIELD_KEY = "edit_field"

_FIELD_ATTR = {
    "q":    "q",
    "ans":  "answer",
    "expl": "explanation",
    "opts": "opts",
    "hint": "hint",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _show_category_list(query, engine: LearningEngine) -> None:
    cats = engine.bank.categories()
    cats_with_counts = [(cat, len(engine.bank.by_category(cat))) for cat in cats]
    total = sum(c for _, c in cats_with_counts)
    await query.edit_message_text(
        f"📋 <b>Question Bank</b>  ({total} total)\n\nSelect a category:",
        parse_mode="HTML",
        reply_markup=category_list_keyboard(cats_with_counts),
    )


async def _show_question_detail(query, qid: str, engine: LearningEngine) -> None:
    q = engine.bank.get(qid)
    if not q:
        await query.edit_message_text("Question not found.")
        return
    is_custom = engine.storage.is_custom_question(qid)

    opts_text = ""
    if q.opts:
        opts_text = "\n<b>Options:</b>\n" + "\n".join(
            f"  {'✅' if i == int(q.answer) else '▫️'} {chr(65 + i)}. {escape(o)}"
            for i, o in enumerate(q.opts)
        )

    text = (
        f"📝 <b>Question detail</b>\n\n"
        f"<b>ID:</b> <code>{escape(qid)}</code>\n"
        f"<b>Type:</b> {escape(q.type)}  "
        f"<b>Difficulty:</b> {escape(q.difficulty)}\n"
        f"<b>Category:</b> {escape(q.cat)}\n\n"
        f"<b>Q:</b> {escape(q.q)}"
        f"{opts_text}\n\n"
        f"<b>Answer:</b> {escape(q.correct_answer_text())}\n"
        f"<b>Explanation:</b> {escape(q.explanation or '—')}"
        + (f"\n<b>Hint:</b> {escape(q.hint)}" if q.hint else "")
        + ("\n\n<i>[custom / edited]</i>" if is_custom else "")
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=question_detail_keyboard(qid, is_custom),
    )


# ------------------------------------------------------------------
# Browse callbacks (stateless, registered in main.py)
# ------------------------------------------------------------------

async def list_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    cats = engine.bank.categories()
    cats_with_counts = [(cat, len(engine.bank.by_category(cat))) for cat in cats]
    total = sum(c for _, c in cats_with_counts)
    await update.effective_message.reply_text(
        f"📋 <b>Question Bank</b>  ({total} total)\n\nSelect a category:",
        parse_mode="HTML",
        reply_markup=category_list_keyboard(cats_with_counts),
    )


async def list_browse_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    engine: LearningEngine = ctx.bot_data["engine"]
    route = query.data

    if route in ("ql_list", "ql_noop"):
        await _show_category_list(query, engine)
        return

    if route.startswith("ql_c_"):
        # ql_c_{cat}_{page} — cat may contain underscores; page is the last segment
        rest = route[5:]
        cat, _, pg_str = rest.rpartition("_")
        page = int(pg_str)
        questions = engine.bank.by_category(cat)
        total_pages = max(1, (len(questions) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_qs = questions[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]
        await query.edit_message_text(
            f"📂 <b>{escape(cat)}</b>  ({len(questions)} questions, page {page + 1}/{total_pages})",
            parse_mode="HTML",
            reply_markup=question_list_keyboard(page_qs, cat, page, total_pages),
        )
        return

    if route.startswith("ql_q_"):
        await _show_question_detail(query, route[5:], engine)
        return

    if route.startswith("ql_d_"):
        qid = route[5:]
        q = engine.bank.get(qid)
        if not q:
            await query.edit_message_text("Question not found.")
            return
        await query.edit_message_text(
            f"🗑️ Delete this question?\n\n<i>{escape(q.q[:120])}</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, delete", callback_data=f"ql_dd_{qid}"),
                 InlineKeyboardButton("❌ Cancel",      callback_data=f"ql_q_{qid}")],
            ]),
        )
        return

    if route.startswith("ql_dd_"):
        qid = route[6:]
        engine.delete_question(qid)
        await query.edit_message_text(
            "✅ Question deleted.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Back to categories", callback_data="ql_list"),
            ]]),
        )
        return


# ------------------------------------------------------------------
# Edit ConversationHandler
# ------------------------------------------------------------------

async def edit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    qid = query.data[5:]  # ql_e_{qid}
    engine: LearningEngine = ctx.bot_data["engine"]
    q = engine.bank.get(qid)
    if not q:
        await query.edit_message_text("Question not found.")
        return ConversationHandler.END

    ctx.user_data[_EDIT_Q_KEY] = qid
    ctx.user_data[_EDIT_FIELD_KEY] = None

    await query.edit_message_text(
        f"✏️ Editing:\n<i>{escape(q.q[:80])}</i>\n\nSelect field to change:",
        parse_mode="HTML",
        reply_markup=edit_field_keyboard(),
    )
    return EDIT_SELECT_FIELD


async def edit_pick_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    engine: LearningEngine = ctx.bot_data["engine"]
    await query.edit_message_text(
        "Select new category:",
        reply_markup=edit_category_keyboard(engine.bank.categories()),
    )
    return EDIT_SELECT_CAT


async def edit_pick_diff(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Select new difficulty:",
        reply_markup=edit_difficulty_keyboard(),
    )
    return EDIT_SELECT_DIFF


async def edit_prompt_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data[3:]  # ef_q → "q", ef_ans → "ans", etc.
    ctx.user_data[_EDIT_FIELD_KEY] = field

    prompts = {
        "q":    "Enter new question text:",
        "ans":  "Enter new answer\n(for mc: letter A/B/C/D — for fill: exact answer text):",
        "expl": "Enter new explanation (or send /skip to clear it):",
        "opts": "Enter new options, one per line (mc only, at least 2):",
        "hint": "Enter new hint (or /skip to clear it):",
    }
    await query.edit_message_text(prompts.get(field, "Enter new value:"))
    return EDIT_ENTER_TEXT


async def edit_save_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    new_cat = query.data[4:]  # efc_{cat}
    return await _apply_change(query, ctx, cat=new_cat)


async def edit_save_diff(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    new_diff = query.data[4:]  # efd_{diff}
    return await _apply_change(query, ctx, difficulty=new_diff)


async def edit_save_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    field = ctx.user_data.get(_EDIT_FIELD_KEY)
    qid = ctx.user_data.get(_EDIT_Q_KEY)
    engine: LearningEngine = ctx.bot_data["engine"]
    q = engine.bank.get(qid)
    if not q:
        await update.message.reply_text("Question not found. Edit cancelled.")
        return ConversationHandler.END

    kwargs: dict = {}
    if field == "q":
        kwargs["q"] = text
    elif field == "ans":
        if q.type in ("mc", "reading"):
            letter = text.upper()
            if letter in "ABCD" and ord(letter) - 65 < len(q.opts):
                kwargs["answer"] = ord(letter) - 65
            else:
                await update.message.reply_text(
                    f"❌ Invalid letter. Use A–{chr(64 + len(q.opts))}.\nSelect field to edit:",
                    reply_markup=edit_field_keyboard(),
                )
                return EDIT_SELECT_FIELD
        else:
            kwargs["answer"] = text
    elif field == "expl":
        kwargs["explanation"] = text
    elif field == "opts":
        opts = [line.strip() for line in text.splitlines() if line.strip()]
        if len(opts) < 2:
            await update.message.reply_text(
                "❌ Need at least 2 options. Select field to edit:",
                reply_markup=edit_field_keyboard(),
            )
            return EDIT_SELECT_FIELD
        kwargs["opts"] = opts
    elif field == "hint":
        kwargs["hint"] = text

    q_new = replace(q, **kwargs)
    engine.edit_question(q_new)
    await update.message.reply_text(
        "✅ Saved. Select field to edit:",
        reply_markup=edit_field_keyboard(),
    )
    return EDIT_SELECT_FIELD


async def edit_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /skip in text-entry step — clears explanation or hint."""
    field = ctx.user_data.get(_EDIT_FIELD_KEY)
    if field in ("expl", "hint"):
        attr = "explanation" if field == "expl" else "hint"
        qid = ctx.user_data.get(_EDIT_Q_KEY)
        engine: LearningEngine = ctx.bot_data["engine"]
        q = engine.bank.get(qid)
        if q:
            engine.edit_question(replace(q, **{attr: ""}))
    await update.message.reply_text(
        "✅ Field cleared. Select field to edit:",
        reply_markup=edit_field_keyboard(),
    )
    return EDIT_SELECT_FIELD


async def edit_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    qid = ctx.user_data.get(_EDIT_Q_KEY)
    engine: LearningEngine = ctx.bot_data["engine"]
    await _show_question_detail(query, qid, engine)
    ctx.user_data.pop(_EDIT_Q_KEY, None)
    ctx.user_data.pop(_EDIT_FIELD_KEY, None)
    return ConversationHandler.END


async def edit_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Edit cancelled.")
    ctx.user_data.pop(_EDIT_Q_KEY, None)
    ctx.user_data.pop(_EDIT_FIELD_KEY, None)
    return ConversationHandler.END


async def _apply_change(query, ctx: ContextTypes.DEFAULT_TYPE, **kwargs) -> int:
    qid = ctx.user_data.get(_EDIT_Q_KEY)
    engine: LearningEngine = ctx.bot_data["engine"]
    q = engine.bank.get(qid)
    if q:
        engine.edit_question(replace(q, **kwargs))
    field_name = list(kwargs.keys())[0]
    new_val = list(kwargs.values())[0]
    await query.edit_message_text(
        f"✅ {field_name.capitalize()} → <b>{escape(str(new_val))}</b>\n\nSelect field to edit:",
        parse_mode="HTML",
        reply_markup=edit_field_keyboard(),
    )
    return EDIT_SELECT_FIELD


def build_edit_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_start, pattern=r"^ql_e_")],
        states={
            EDIT_SELECT_FIELD: [
                CallbackQueryHandler(edit_pick_cat,   pattern=r"^ef_cat$"),
                CallbackQueryHandler(edit_pick_diff,  pattern=r"^ef_diff$"),
                CallbackQueryHandler(edit_prompt_text, pattern=r"^ef_(q|ans|expl|opts|hint)$"),
                CallbackQueryHandler(edit_done,        pattern=r"^ef_done$"),
            ],
            EDIT_SELECT_CAT: [
                CallbackQueryHandler(edit_save_cat, pattern=r"^efc_"),
            ],
            EDIT_SELECT_DIFF: [
                CallbackQueryHandler(edit_save_diff, pattern=r"^efd_"),
            ],
            EDIT_ENTER_TEXT: [
                CommandHandler("skip", edit_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", edit_cancel)],
        per_message=False,
    )
