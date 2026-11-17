import logging
from datetime import time

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop, ContextTypes, MessageHandler, TypeHandler, filters

from app.bot.budget import remind_point
from app.bot.common import show_main_menu
from app.bot.conversation import build_conversation_handler
from app.core.clock import PARIS
from app.core.config import TELEGRAM_ALLOWED_USER_ID, TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# La paie tombe en fin de mois : le 1er au matin, elle est forcément arrivée.
_POINT_REMINDER_DAY = 1
_POINT_REMINDER_TIME = time(9, 0, tzinfo=PARIS)


async def _reject_strangers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Bot strictement personnel : tout autre utilisateur est ignoré avant d'atteindre un handler.
    user = update.effective_user
    if user is None or user.id != TELEGRAM_ALLOWED_USER_ID:
        raise ApplicationHandlerStop


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, (NetworkError, TimedOut)):
        return
    logger.error("Erreur inattendue", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text("⚠️ Une erreur est survenue. Réessaie dans un instant.")


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(TypeHandler(Update, _reject_strangers), group=-1)
    app.add_handler(build_conversation_handler())
    # Tout message hors parcours ramène au menu principal.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_main_menu))
    app.add_error_handler(_on_error)
    if app.job_queue is None:
        raise RuntimeError("JobQueue absente : installer python-telegram-bot[job-queue]")
    app.job_queue.run_monthly(
        remind_point,
        when=_POINT_REMINDER_TIME,
        day=_POINT_REMINDER_DAY,
        chat_id=TELEGRAM_ALLOWED_USER_ID,
        name="monthly_point",
    )
    app.run_polling()


if __name__ == "__main__":
    main()
