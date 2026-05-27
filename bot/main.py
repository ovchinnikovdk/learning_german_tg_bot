"""Telegram bot entry point."""
from __future__ import annotations

import datetime
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.handlers.add_question import build_add_question_handler
from bot.handlers.daily import daily_answer_callback, daily_command, send_daily_push
from bot.handlers.generate import candidates_callback, candidates_command, generate_command
from bot.handlers.learn import (
    learn_command,
    learn_fill_message,
    learn_mc_callback,
    learn_next_callback,
)
from bot.handlers.list_questions import build_edit_handler, list_browse_callback, list_command
from bot.handlers.stats import stats_command, stats_download_callback
from bot.keyboards import main_menu_keyboard
from config import settings
from core.engine import LearningEngine
from shared.factory import build_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    user = update.effective_user
    engine.register_user(user.id, user.id, user.first_name or "")
    await update.message.reply_text(
        f"Hallo {user.first_name}! 🇩🇪\n\n"
        "I'll help you practice German with daily questions and spaced repetition.\n\n"
        "Choose an action:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    route = query.data

    if route == "menu_daily":
        await daily_command(update, ctx)
    elif route == "menu_learn":
        await learn_command(update, ctx)
    elif route == "menu_stats":
        await stats_command(update, ctx)
    elif route == "menu_add":
        await query.message.reply_text("Use /add to add a new question.")
    elif route == "menu_list":
        await list_command(update, ctx)
    elif route == "menu_generate":
        await generate_command(update, ctx)
    elif route == "menu_main":
        await query.message.reply_text("Main menu:", reply_markup=main_menu_keyboard())


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=ctx.error)


async def daily_backup_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    engine: LearningEngine = ctx.bot_data["engine"]
    stats_path, questions_path = engine.backup()
    logger.info("Daily backup: stats → %s, questions → %s", stats_path, questions_path)


async def daily_routine_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """9am daily: push questions to all users, then generate 5 AI candidates."""
    engine: LearningEngine = ctx.bot_data["engine"]
    users = engine.get_all_users()

    # 1. Push daily question to every registered user
    logger.info("Daily routine: sending questions to %d user(s)", len(users))
    for user in users:
        try:
            await send_daily_push(ctx.bot, user.chat_id, user.user_id, engine)
        except Exception as exc:
            logger.warning("Daily push failed for user %s: %s", user.user_id, exc)

    # 2. Generate 5 AI question candidates (personalized to first user's stats)
    ref_user_id = users[0].user_id if users else 0
    try:
        candidates = await engine.generate_candidates(ref_user_id)
        logger.info("Daily AI generation: created %d candidate(s)", len(candidates))
    except Exception as exc:
        logger.warning("Daily AI generation failed: %s", exc)


def build_app() -> Application:
    engine = build_engine()

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["engine"] = engine

    # Commands
    app.add_handler(CommandHandler("start",      start_command))
    app.add_handler(CommandHandler("daily",      daily_command))
    app.add_handler(CommandHandler("learn",      learn_command))
    app.add_handler(CommandHandler("stats",      stats_command))
    app.add_handler(CommandHandler("list",       list_command))
    app.add_handler(CommandHandler("generate",   generate_command))
    app.add_handler(CommandHandler("candidates", candidates_command))

    # ConversationHandlers must come before generic callbacks
    app.add_handler(build_add_question_handler())
    app.add_handler(build_edit_handler())

    # Inline button callbacks — most specific patterns first
    app.add_handler(CallbackQueryHandler(menu_callback,       pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(learn_next_callback, pattern=r"^learn_next$"))
    app.add_handler(CallbackQueryHandler(learn_mc_callback,   pattern=r"^learn_\d$"))
    app.add_handler(CallbackQueryHandler(daily_answer_callback, pattern=r"^daily_\d$"))

    # List / browse callbacks
    app.add_handler(CallbackQueryHandler(list_browse_callback, pattern=r"^ql_"))

    # Candidate callbacks
    app.add_handler(CallbackQueryHandler(candidates_callback, pattern=r"^cand_"))

    # Stats download
    app.add_handler(CallbackQueryHandler(stats_download_callback, pattern=r"^stats_dl$"))

    # Text messages → fill-in-the-blank answers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, learn_fill_message))

    app.add_error_handler(error_handler)

    # Scheduled jobs
    app.job_queue.run_daily(
        daily_backup_job,
        time=datetime.time(0, 0, 0),
    )
    app.job_queue.run_daily(
        daily_routine_job,
        time=datetime.time(settings.daily_push_hour_utc, 0, 0),
    )

    return app


def main() -> None:
    app = build_app()
    logger.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
