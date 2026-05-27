"""Inline keyboard builders for Telegram UI."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.models import Question

PAGE_SIZE = 8


# ------------------------------------------------------------------
# Core / shared
# ------------------------------------------------------------------

def mc_keyboard(question: Question, prefix: str = "ans") -> InlineKeyboardMarkup:
    """One button per MC option. prefix distinguishes daily_N from learn_N callbacks."""
    buttons = [
        [InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"{prefix}_{i}")]
        for i, opt in enumerate(question.opts)
    ]
    return InlineKeyboardMarkup(buttons)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Daily question", callback_data="menu_daily")],
        [InlineKeyboardButton("🎓 Learn mode",     callback_data="menu_learn")],
        [InlineKeyboardButton("📊 My stats",        callback_data="menu_stats")],
        [InlineKeyboardButton("➕ Add question",    callback_data="menu_add")],
        [InlineKeyboardButton("📋 List questions",  callback_data="menu_list")],
        [InlineKeyboardButton("🤖 Generate (AI)",   callback_data="menu_generate")],
    ])


def confirm_keyboard(yes_data: str = "confirm_yes", no_data: str = "confirm_no") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data=yes_data),
        InlineKeyboardButton("❌ No",  callback_data=no_data),
    ]])


def category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
    return InlineKeyboardMarkup(buttons)


def difficulty_keyboard() -> InlineKeyboardMarkup:
    levels = ["A1", "A2", "B1", "B2"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lv, callback_data=f"diff_{lv}") for lv in levels]
    ])


def question_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Multiple choice",    callback_data="type_mc")],
        [InlineKeyboardButton("Fill in the blank",  callback_data="type_fill")],
    ])


def next_question_keyboard(callback: str = "learn_next") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Next question", callback_data=callback)],
        [InlineKeyboardButton("🏠 Main menu",     callback_data="menu_main")],
    ])


# ------------------------------------------------------------------
# List / browse keyboards
# ------------------------------------------------------------------

def category_list_keyboard(cats_with_counts: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"📂 {cat}  ({count})", callback_data=f"ql_c_{cat}_0")]
        for cat, count in cats_with_counts
    ]
    buttons.append([InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def question_list_keyboard(
    questions: list[Question],
    cat: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    buttons = []
    for q in questions:
        label = q.q[:38] + "…" if len(q.q) > 38 else q.q
        buttons.append([InlineKeyboardButton(
            f"[{q.difficulty}] {label}",
            callback_data=f"ql_q_{q.id}",
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"ql_c_{cat}_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ql_noop"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"ql_c_{cat}_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("◀️ Categories", callback_data="ql_list")])
    return InlineKeyboardMarkup(buttons)


def question_detail_keyboard(qid: str, is_custom: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("✏️ Edit", callback_data=f"ql_e_{qid}")]]
    if is_custom:
        rows.append([InlineKeyboardButton("🗑️ Delete", callback_data=f"ql_d_{qid}")])
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="ql_list")])
    return InlineKeyboardMarkup(rows)


# ------------------------------------------------------------------
# Edit keyboards (used inside ConversationHandler)
# ------------------------------------------------------------------

def edit_field_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Category",       callback_data="ef_cat"),
         InlineKeyboardButton("📶 Difficulty",     callback_data="ef_diff")],
        [InlineKeyboardButton("❓ Question text",  callback_data="ef_q")],
        [InlineKeyboardButton("✅ Answer",         callback_data="ef_ans"),
         InlineKeyboardButton("💡 Explanation",   callback_data="ef_expl")],
        [InlineKeyboardButton("📝 Options (mc)",   callback_data="ef_opts"),
         InlineKeyboardButton("🔑 Hint (fill)",   callback_data="ef_hint")],
        [InlineKeyboardButton("✅ Done editing",   callback_data="ef_done")],
    ])


def edit_category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(cat, callback_data=f"efc_{cat}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(buttons)


def edit_difficulty_keyboard() -> InlineKeyboardMarkup:
    levels = ["A1", "A2", "B1", "B2"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(lv, callback_data=f"efd_{lv}") for lv in levels
    ]])


# ------------------------------------------------------------------
# Candidate (LLM-generated) keyboards
# ------------------------------------------------------------------

def candidate_list_keyboard(candidates: list[dict]) -> InlineKeyboardMarkup:
    def _src_icon(src: str) -> str:
        return "☁️" if src == "anthropic" else "🖥️"

    buttons = [
        [InlineKeyboardButton(
            f"{_src_icon(c.get('source', 'local'))} #{i + 1}: {c['question_data'].get('q', '?')[:33]}…",
            callback_data=f"cand_v_{c['id']}",
        )]
        for i, c in enumerate(candidates)
    ]
    buttons.append([InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def candidate_detail_keyboard(cid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve",         callback_data=f"cand_ok_{cid}"),
         InlineKeyboardButton("❌ Reject",          callback_data=f"cand_no_{cid}")],
        [InlineKeyboardButton("◀️ Back to list",    callback_data="cand_list")],
    ])
