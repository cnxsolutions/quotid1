import logging
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from app.bot.handlers import start, dep, rev, todo, today, done, cash, mois, message_handler
from app.bot.conversation import build_conversation_handler
from app.core.charges import apply_monthly_charges
from app.core.tasks import get_pending_tasks, get_tasks_due_tomorrow, get_tasks_due_in_days
from app.bot.conversation import _format_tasks
from app.core.weekly_report import generate_weekly_report

PARIS = ZoneInfo("Europe/Paris")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


async def _error_handler(update, context) -> None:
    if isinstance(context.error, (NetworkError, TimedOut)):
        return
    logging.error("Erreur inattendue : %s", context.error)


async def _run_monthly_charges(context) -> None:
    now = datetime.now(timezone.utc)
    applied = apply_monthly_charges(now.year, now.month)
    if applied:
        msg = "📦 Charges du mois appliquées :\n" + "\n".join(f"  • {n}" for n in applied)
        await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _daily_task_report(context) -> None:
    tasks = get_pending_tasks()
    if not tasks:
        return
    msg = "📋 Tâches du jour :\n\n" + _format_tasks(tasks)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _remind_due_tomorrow(context) -> None:
    tasks = get_tasks_due_tomorrow()
    if not tasks:
        return
    msg = "⏰ Rappel — échéance demain :\n\n" + _format_tasks(tasks)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _remind_due_in_3_days(context) -> None:
    tasks = get_tasks_due_in_days(3)
    if not tasks:
        return
    msg = "📅 Échéance dans 3 jours :\n\n" + _format_tasks(tasks)
    await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)


async def _weekly_ai_report(context) -> None:
    try:
        report = generate_weekly_report()
        msg = "📊 Rapport hebdomadaire IA\n\n" + report
        await context.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=msg)
    except Exception as e:
        logging.error("Erreur rapport hebdomadaire : %s", e)


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_error_handler(_error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dep", dep))
    app.add_handler(CommandHandler("rev", rev))
    app.add_handler(CommandHandler("todo", todo))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("cash", cash))
    app.add_handler(CommandHandler("mois", mois))
    app.add_handler(build_conversation_handler())
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.job_queue.run_monthly(
        _run_monthly_charges,
        when=time(8, 0, tzinfo=PARIS),
        day=1,
    )
    app.job_queue.run_once(_run_monthly_charges, when=5)
    app.job_queue.run_daily(_daily_task_report, time=time(5, 0, tzinfo=PARIS))
    app.job_queue.run_daily(_remind_due_tomorrow, time=time(20, 0, tzinfo=PARIS))
    app.job_queue.run_daily(_remind_due_in_3_days, time=time(20, 0, tzinfo=PARIS))
    app.job_queue.run_daily(_weekly_ai_report, time=time(8, 0, tzinfo=PARIS), days=(0,))
    app.run_polling()


if __name__ == "__main__":
    main()
