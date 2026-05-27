"""Handler for /generate — LLM-powered question generation.

Flow:
  /generate or menu_generate
    → sends "Generating…" message
    → calls LLM, stores candidates
    → shows count + button to review

  /candidates or cand_list callback
    → lists pending candidates with numbered buttons

  cand_v_{cid}   → show candidate detail (question preview + Approve/Reject)
  cand_ok_{cid}  → approve → add to bank
  cand_no_{cid}  → reject → mark rejected
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.formatting import escape
from bot.keyboards import candidate_detail_keyboard, candidate_list_keyboard
from core.engine import LearningEngine

logger = logging.getLogger(__name__)


async def generate_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user = update.effective_user
    engine.register_user(user.id, user.id, user.first_name or "")
    msg = update.effective_message

    waiting = await msg.reply_text(
        "🤖 Generating questions via LLM…\n\nThis may take up to 60 seconds.",
    )

    try:
        candidates = await engine.generate_candidates(user.id)
        if candidates:
            await waiting.edit_text(
                f"✅ Generated <b>{len(candidates)}</b> question candidate(s)!\n\n"
                "Review them below, then approve to add to the bank.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Review candidates", callback_data="cand_list"),
                ]]),
            )
        else:
            await waiting.edit_text(
                "⚠️ LLM responded but no valid questions were parsed.\n"
                "Try again or check the model output."
            )
    except Exception as exc:
        logger.error("LLM generation error: %s", exc, exc_info=True)
        from config import settings
        await waiting.edit_text(
            f"❌ Generation failed:\n<code>{escape(str(exc)[:200])}</code>\n\n"
            f"Make sure Ollama is running at {escape(settings.ollama_url)}",
            parse_mode="HTML",
        )


async def candidates_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    pending = engine.get_pending_candidates()
    if not pending:
        await update.effective_message.reply_text(
            "No pending candidates.\n\nUse /generate to create new ones.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤖 Generate now", callback_data="menu_generate"),
            ]]),
        )
        return
    await update.effective_message.reply_text(
        f"📋 <b>{len(pending)} pending candidate(s)</b>\n\nTap to review:",
        parse_mode="HTML",
        reply_markup=candidate_list_keyboard(pending),
    )


async def candidates_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    engine: LearningEngine = ctx.bot_data["engine"]
    route = query.data

    if route == "cand_list":
        pending = engine.get_pending_candidates()
        if not pending:
            await query.edit_message_text(
                "No pending candidates.\n\nUse /generate to create new ones.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🤖 Generate now", callback_data="menu_generate"),
                    InlineKeyboardButton("🏠 Menu",         callback_data="menu_main"),
                ]]),
            )
            return
        await query.edit_message_text(
            f"📋 <b>{len(pending)} pending candidate(s)</b>\n\nTap to review:",
            parse_mode="HTML",
            reply_markup=candidate_list_keyboard(pending),
        )
        return

    if route.startswith("cand_v_"):
        cid = route[7:]
        await _show_candidate(query, cid, engine)
        return

    if route.startswith("cand_ok_"):
        cid = route[8:]
        q = engine.approve_candidate(cid)
        if q:
            await query.edit_message_text(
                f"✅ Approved and added to bank!\n\n"
                f"<b>ID:</b> <code>{escape(q.id)}</code>\n"
                f"<b>Category:</b> {escape(q.cat)}  <b>Difficulty:</b> {escape(q.difficulty)}\n\n"
                f"<i>{escape(q.q)}</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Back to list", callback_data="cand_list"),
                ]]),
            )
        else:
            await query.edit_message_text("Candidate not found.")
        return

    if route.startswith("cand_no_"):
        cid = route[8:]
        engine.reject_candidate(cid)
        pending = engine.get_pending_candidates()
        remaining = len(pending)
        await query.edit_message_text(
            f"❌ Rejected.  {remaining} candidate(s) remaining.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Back to list", callback_data="cand_list"),
            ]]),
        )
        return


async def _show_candidate(query, cid: str, engine: LearningEngine) -> None:
    raw = engine.storage.get_candidate(cid)
    if not raw:
        await query.edit_message_text("Candidate not found.")
        return
    d = raw["question_data"]
    opts_text = ""
    if d.get("opts"):
        opts_text = "\n<b>Options:</b>\n" + "\n".join(
            f"  {'✅' if i == d.get('answer') else '▫️'} {chr(65 + i)}. {escape(str(o))}"
            for i, o in enumerate(d["opts"])
        )

    source = raw.get("source", "local")
    source_label = "☁️ Claude (Anthropic)" if source == "anthropic" else "🖥️ Local LLM"

    text = (
        f"🤖 <b>Candidate question</b>  <i>{escape(source_label)}</i>\n\n"
        f"<b>Category:</b> {escape(d.get('cat', '?'))}  "
        f"<b>Difficulty:</b> {escape(d.get('difficulty', '?'))}\n\n"
        f"<b>Q:</b> {escape(d.get('q', '?'))}"
        f"{opts_text}\n\n"
        f"<b>Answer:</b> {escape(str(d.get('answer', '?')))}\n"
        f"<b>Explanation:</b> {escape(d.get('explanation', '—'))}"
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=candidate_detail_keyboard(cid),
    )
