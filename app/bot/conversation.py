"""Assemblage du bot : navigation, étapes de chaque parcours, expiration."""

from telegram import Update
from telegram.ext import BaseHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.bot import budget, sections
from app.bot import keyboards as kb
from app.bot.common import State, peek_flow, set_flow, show_main_menu

Handler = BaseHandler[Update, ContextTypes.DEFAULT_TYPE, object]

_INACTIVITY_TIMEOUT_SECONDS = 600


async def on_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = peek_flow(context)
    set_flow(context, None)
    # Rester sur un menu sans rien faire est normal : on ne prévient que si une saisie était en cours.
    in_progress = isinstance(flow, budget.PointFlow) or sections.is_in_progress(flow)
    if in_progress and update.effective_chat is not None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏰ Saisie abandonnée après 10 min d'inactivité, rien n'a été enregistré.",
            reply_markup=kb.MAIN,
        )


def build_conversation_handler() -> ConversationHandler[ContextTypes.DEFAULT_TYPE]:
    # Les boutons du menu principal restent actifs à toutes les étapes.
    navigation: list[Handler] = [
        MessageHandler(filters.Text([kb.BTN_POINT]), budget.start_point),
        MessageHandler(filters.Text([kb.BTN_OVERVIEW]), budget.show_overview),
        MessageHandler(filters.Text([kb.BTN_ACCOUNTS]), sections.open_accounts),
        MessageHandler(filters.Text([kb.BTN_CHARGES]), sections.open_charges),
        MessageHandler(filters.Text([kb.BTN_INCOMES]), sections.open_incomes),
        MessageHandler(filters.Text([kb.BTN_SAVINGS]), sections.open_savings),
    ]
    text = filters.TEXT & ~filters.COMMAND
    steps = {
        State.MENU: sections.on_menu,
        State.PICK: sections.on_pick,
        State.NAME: sections.on_name,
        State.AMOUNT: sections.on_amount,
        State.FREQUENCY: sections.on_frequency,
        State.KIND: sections.on_kind,
        State.DUE_MONTH: sections.on_due_month,
        State.DEADLINE: sections.on_deadline,
        State.TARGET: sections.on_target,
        State.CONFIRM_DELETE: sections.on_confirm_delete,
        State.POINT_BALANCE: budget.on_point_balance,
        State.POINT_INCOME: budget.on_point_income,
    }
    states: dict[object, list[Handler]] = {
        state: [*navigation, MessageHandler(text, callback)] for state, callback in steps.items()
    }
    states[ConversationHandler.TIMEOUT] = [MessageHandler(filters.ALL, on_timeout)]
    return ConversationHandler(
        entry_points=[CommandHandler("start", show_main_menu), *navigation],
        states=states,
        fallbacks=[CommandHandler(["start", "annuler", "cancel"], show_main_menu)],
        conversation_timeout=_INACTIVITY_TIMEOUT_SECONDS,
    )
