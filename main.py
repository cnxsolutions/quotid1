import logging
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from app.bot.handlers import start, message_handler
from app.bot.conversation import build_conversation_handler, _format_tasks, _format_tasks_report
from app.core.tasks import get_pending_tasks, get_tasks_due_tomorrow, get_tasks_due_in_days
from app.core.weekly_report import generate_weekly_report
from app.core.hadith import get_random_hadith, format_hadith

PARIS = ZoneInfo("Europe/Paris")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


async def _error_handler(update, context) -> None:
    if isinstance(context.error, (NetworkError, TimedOut)):
        return
    logging.error("Erreur inattendue : %s", context.error)


async def _daily_task_report(context) -> None:
    tasks = get_pending_tasks()
    if not tasks:
        return
    msg = _format_tasks_report(tasks, "☀️ BONJOUR — TES TÂCHES")
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _remind_due_tomorrow(context) -> None:
    tasks = get_tasks_due_tomorrow()
    if not tasks:
        return
    msg = "⏰ ÉCHÉANCE DEMAIN\n\n"
    msg += _format_tasks(tasks)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _remind_due_in_3_days(context) -> None:
    tasks = get_tasks_due_in_days(3)
    if not tasks:
        return
    msg = "📅 ÉCHÉANCE DANS 3 JOURS\n\n"
    msg += _format_tasks(tasks)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _daily_hadith(context) -> None:
    h = get_random_hadith()
    if not h:
        return
    msg = format_hadith(h)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _weekly_ai_report(context) -> None:
    try:
        report = generate_weekly_report()
        msg = f"📊 RAPPORT HEBDOMADAIRE\n\n{report}"
        await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)
    except Exception as e:
        logging.error("Erreur rapport hebdomadaire : %s", e)


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_error_handler(_error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(build_conversation_handler())
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Jobs uniques pour éviter les doublons
    app.job_queue.run_daily(_daily_hadith, time=time(4, 30, tzinfo=PARIS), name="daily_hadith")
    app.job_queue.run_daily(_daily_task_report, time=time(5, 0, tzinfo=PARIS), name="daily_tasks")
    app.job_queue.run_daily(_remind_due_tomorrow, time=time(20, 0, tzinfo=PARIS), name="remind_tomorrow")
    app.job_queue.run_daily(_remind_due_in_3_days, time=time(20, 0, tzinfo=PARIS), name="remind_3days")
    app.job_queue.run_daily(_weekly_ai_report, time=time(8, 0, tzinfo=PARIS), days=(0,), name="weekly_report")
    app.run_polling()


if __name__ == "__main__":
    main()
