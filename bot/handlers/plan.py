"""Handler for /plan — learning plan: AI summary, current topic, history."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.formatting import escape
from bot.handlers.learn import LEARN_Q_KEY, TOPIC_IDS_KEY, _send_question
from core.engine import LearningEngine


# ------------------------------------------------------------------
# Keyboards
# ------------------------------------------------------------------

def _no_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Generate Learning Plan", callback_data="plan_gen")],
        [InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")],
    ])


def _plan_no_topic_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Start Next Topic", callback_data="plan_topic")],
        [InlineKeyboardButton("🔄 Regenerate Plan", callback_data="plan_gen")],
        [InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")],
    ])


def _plan_with_topic_keyboard(history_count: int, has_exercises: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_exercises:
        rows.append([InlineKeyboardButton("🎓 Practice Exercises", callback_data="plan_practice")])
    else:
        rows.append([InlineKeyboardButton("⚙️ Generate Exercises", callback_data="plan_exercises")])
    if history_count:
        rows.append([InlineKeyboardButton(
            f"📖 Topic History ({history_count})", callback_data="plan_history"
        )])
    rows += [
        [InlineKeyboardButton("✅ Complete Topic", callback_data="plan_complete")],
        [InlineKeyboardButton("🔄 Regenerate Plan", callback_data="plan_gen")],
        [InlineKeyboardButton("🏠 Main menu", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(rows)


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------

async def _show_plan(msg, plan: dict) -> None:
    current_topic = plan.get("current_topic")
    history_count = len(plan.get("topics_history", []))

    if current_topic:
        name = current_topic.get("name", "")
        desc = current_topic.get("description", "")
        rules = current_topic.get("grammar_rules", [])
        examples = current_topic.get("examples", [])[:3]
        cats = current_topic.get("focus_categories", [])
        started = current_topic.get("started_at", "")[:10]
        question_ids = current_topic.get("question_ids", [])

        lines = [f"📚 <b>Current Topic:</b> {escape(name)}\n", escape(desc)]
        if rules:
            lines.append("\n<b>Grammar Rules:</b>")
            for r in rules[:6]:
                lines.append(f"  • {escape(r)}")
        if examples:
            lines.append("\n<b>Examples:</b>")
            for e in examples:
                lines.append(f"  • <i>{escape(e.get('german', ''))}</i>  →  {escape(e.get('english', ''))}")
        if cats:
            lines.append(f"\n🎯 <b>Focus:</b> {escape(', '.join(cats))}")
        lines.append(f"📅 Started: {started}")
        if question_ids:
            lines.append(f"📝 <b>Exercises:</b> {len(question_ids)} available")
        if history_count:
            lines.append(f"📖 Completed topics: {history_count}")
        await msg.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_plan_with_topic_keyboard(history_count, has_exercises=bool(question_ids)),
        )
    else:
        summary = plan.get("ai_summary", "")
        progression = plan.get("recommended_progression", [])
        weak = plan.get("weak_areas", [])
        strengths = plan.get("strengths", [])

        lines = ["📚 <b>Your Learning Plan</b>\n"]
        if summary:
            lines.append(escape(summary))
        if progression:
            lines.append("\n<b>Recommended Path:</b>")
            for i, t in enumerate(progression[:8], 1):
                lines.append(f"  {i}. {escape(t)}")
        if weak:
            lines.append(f"\n⚡ <b>Focus areas:</b> {escape(', '.join(weak))}")
        if strengths:
            lines.append(f"✨ <b>Strengths:</b> {escape(', '.join(strengths))}")
        if history_count:
            lines.append(f"\n📖 Completed topics: {history_count}")
        await msg.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_plan_no_topic_keyboard(),
        )


# ------------------------------------------------------------------
# Command + callbacks
# ------------------------------------------------------------------

async def plan_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id
    plan = engine.get_learning_plan(user_id)
    msg = update.effective_message

    if plan is None:
        await msg.reply_text(
            "📚 <b>Learning Plan</b>\n\n"
            "You don't have a personalized learning plan yet.\n\n"
            "Generating a plan analyzes your question bank and performance "
            "to create a tailored learning path with sequenced topics.",
            parse_mode="HTML",
            reply_markup=_no_plan_keyboard(),
        )
        return

    await _show_plan(msg, plan)


async def plan_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    engine: LearningEngine = ctx.bot_data["engine"]
    user_id = update.effective_user.id
    data = query.data

    if data == "plan_gen":
        await query.message.reply_text("⏳ Generating your learning plan… this may take a moment.")
        try:
            plan = await engine.generate_learning_plan(user_id)
            await _show_plan(query.message, plan)
        except Exception as exc:
            await query.message.reply_text(f"❌ Failed to generate plan: {escape(str(exc))}")

    elif data == "plan_topic":
        plan = engine.get_learning_plan(user_id)
        if plan and plan.get("current_topic"):
            await query.message.reply_text(
                "You already have an active topic. Complete it first with ✅ Complete Topic."
            )
            return
        await query.message.reply_text(
            "⏳ Generating your next learning topic and 20 exercises… this may take a moment."
        )
        try:
            await engine.generate_current_topic(user_id)
            plan = engine.get_learning_plan(user_id)
            await _show_plan(query.message, plan)
        except Exception as exc:
            await query.message.reply_text(f"❌ Failed to generate topic: {escape(str(exc))}")

    elif data == "plan_exercises":
        await query.message.reply_text("⏳ Generating 20 exercises for this topic…")
        try:
            count = await engine.ensure_topic_has_exercises(user_id)
            if count:
                plan = engine.get_learning_plan(user_id)
                await _show_plan(query.message, plan)
            else:
                await query.message.reply_text(
                    "⚠️ Exercise generation returned no valid questions. "
                    "Try again later or check LLM connectivity."
                )
        except Exception as exc:
            await query.message.reply_text(f"❌ Exercise generation failed: {escape(str(exc))}")

    elif data == "plan_practice":
        plan = engine.get_learning_plan(user_id)
        current_topic = plan.get("current_topic") if plan else None
        if not current_topic or not current_topic.get("question_ids"):
            await query.message.reply_text(
                "No exercises yet. Tap ⚙️ Generate Exercises first."
            )
            return
        q = engine.get_topic_learn_question(user_id, current_topic["question_ids"])
        if not q:
            await query.message.reply_text(
                "✅ You've answered all topic exercises! "
                "Use /learn for more practice or complete this topic."
            )
            return
        ctx.user_data[TOPIC_IDS_KEY] = current_topic["question_ids"]
        ctx.user_data[LEARN_Q_KEY] = q.id
        await _send_question(query.message, q, engine, mode_prefix="📚 <b>Topic Practice</b>\n\n")

    elif data == "plan_complete":
        engine.complete_current_topic(user_id)
        ctx.user_data.pop(TOPIC_IDS_KEY, None)
        plan = engine.get_learning_plan(user_id)
        await query.message.reply_text("✅ Topic marked as complete!")
        if plan:
            await _show_plan(query.message, plan)

    elif data == "plan_history":
        plan = engine.get_learning_plan(user_id)
        if not plan or not plan.get("topics_history"):
            await query.message.reply_text("No completed topics yet.")
            return
        history = plan["topics_history"]
        rows = []
        for t in history:
            label = t["name"][:40]
            completed = t.get("completed_at", "")[:10]
            ex_count = len(t.get("question_ids", []))
            suffix = f"  ✅ {completed}" if completed else ""
            rows.append([InlineKeyboardButton(
                f"📖 {label}{suffix}",
                callback_data=f"plan_hist_{t['id']}",
            )])
        rows.append([InlineKeyboardButton("◀️ Back", callback_data="menu_plan")])
        await query.message.reply_text(
            f"📖 <b>Topic History</b> ({len(history)} completed)",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    elif data.startswith("plan_hist_"):
        topic_id = data[len("plan_hist_"):]
        plan = engine.get_learning_plan(user_id)
        history = plan.get("topics_history", []) if plan else []
        topic = next((t for t in history if t.get("id") == topic_id), None)
        if not topic:
            await query.message.reply_text("Topic not found in history.")
            return
        question_ids = topic.get("question_ids", [])
        name = topic.get("name", "")
        desc = topic.get("description", "")
        rules = topic.get("grammar_rules", [])
        completed = topic.get("completed_at", "")[:10]
        lines = [f"📖 <b>{escape(name)}</b>  ✅ {completed}\n", escape(desc)]
        if rules:
            lines.append("\n<b>Grammar Rules:</b>")
            for r in rules[:6]:
                lines.append(f"  • {escape(r)}")
        if question_ids:
            lines.append(f"\n📝 {len(question_ids)} exercises available")
        rows = []
        if question_ids:
            rows.append([InlineKeyboardButton("🎓 Practice Exercises", callback_data=f"plan_hist_practice_{topic_id}")])
        rows.append([InlineKeyboardButton("◀️ Back to History", callback_data="plan_history")])
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    elif data.startswith("plan_hist_practice_"):
        topic_id = data[len("plan_hist_practice_"):]
        plan = engine.get_learning_plan(user_id)
        history = plan.get("topics_history", []) if plan else []
        topic = next((t for t in history if t.get("id") == topic_id), None)
        if not topic or not topic.get("question_ids"):
            await query.message.reply_text("No exercises found for this topic.")
            return
        q = engine.get_topic_learn_question(user_id, topic["question_ids"])
        if not q:
            await query.message.reply_text("✅ You've answered all exercises for this topic!")
            return
        ctx.user_data[TOPIC_IDS_KEY] = topic["question_ids"]
        ctx.user_data[LEARN_Q_KEY] = q.id
        await _send_question(
            query.message, q, engine,
            mode_prefix=f"📖 <b>{escape(topic['name'])}</b>\n\n",
        )
