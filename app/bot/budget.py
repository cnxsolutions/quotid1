"""Point du mois, vue globale et rappel mensuel."""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from app.bot import keyboards as kb
from app.bot import views
from app.bot.common import State, get_flow, reply, set_flow, show_main_menu, text_of
from app.bot.money import format_eur, parse_amount
from app.core.clock import today
from app.core.models import ZERO, Account, closed_month
from app.core.monthly_point import PointDraft, is_point_done, prepare_point, save_point, upcoming_charges
from app.core.overview import load_overview


@dataclass
class PointFlow:
    draft: PointDraft
    balances: dict[int, Decimal] = field(default_factory=dict)

    @property
    def current_account(self) -> Account | None:
        index = len(self.balances)
        return self.draft.accounts[index] if index < len(self.draft.accounts) else None

    @property
    def income_button(self) -> str | None:
        if self.draft.monthly_fixed_incomes <= 0:
            return None
        return f"✅ {format_eur(self.draft.expected_income)}"


# ── Vue globale ──────────────────────────────────────────────────────────────


async def show_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    set_flow(context, None)
    overview = await asyncio.to_thread(load_overview)
    await reply(update, views.render_overview(overview, today()), kb.MAIN)
    return ConversationHandler.END


# ── Point du mois ────────────────────────────────────────────────────────────


async def start_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = await asyncio.to_thread(prepare_point, today())
    if not draft.accounts:
        return await show_main_menu(
            update, context, f"Ajoute d'abord tes comptes ({kb.BTN_ACCOUNTS} → {kb.BTN_ADD}) pour faire le point."
        )
    flow = PointFlow(draft)
    set_flow(context, flow)
    return await _ask_next(update, context, flow, views.render_point_intro(draft))


async def _ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: PointFlow, prefix: str) -> int:
    account = flow.current_account
    if account is not None:
        position = len(flow.balances) + 1
        question = views.render_point_account(account, position, len(flow.draft.accounts), today())
        await reply(update, f"{prefix}\n\n{question}", kb.POINT_BALANCE)
        return State.POINT_BALANCE
    if flow.draft.previous is None:
        # Premier point : pas de bilan possible, les revenus de la période ne servent à rien.
        return await _finish_point(update, context, flow, ZERO)
    question = views.render_point_income(flow.draft, today())
    await reply(update, f"{prefix}\n\n{question}", kb.point_income(flow.income_button))
    return State.POINT_INCOME


async def on_point_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, PointFlow)
    raw = text_of(update)
    if raw == kb.BTN_CANCEL_POINT:
        return await _cancel_point(update, context)
    account = flow.current_account
    if account is None:
        raise RuntimeError("Solde reçu alors que tous les comptes sont relevés")
    balance = account.balance if raw == kb.BTN_UNCHANGED else parse_amount(raw)
    if balance is None:
        await reply(
            update, f"❌ Solde invalide. Exemples : 1250,50 · -80 · 0 — ou « {kb.BTN_UNCHANGED} »", kb.POINT_BALANCE
        )
        return State.POINT_BALANCE
    flow.balances[account.id] = balance
    return await _ask_next(update, context, flow, views.render_point_ack(account, balance))


async def on_point_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, PointFlow)
    raw = text_of(update)
    if raw == kb.BTN_CANCEL_POINT:
        return await _cancel_point(update, context)
    income = flow.draft.expected_income if raw == flow.income_button else parse_amount(raw)
    if income is None or income < 0:
        await reply(
            update, "❌ Montant invalide : un nombre positif ou 0, ex. 2500", kb.point_income(flow.income_button)
        )
        return State.POINT_INCOME
    return await _finish_point(update, context, flow, income)


async def _finish_point(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: PointFlow, income: Decimal) -> int:
    day = today()
    outcome = await asyncio.to_thread(save_point, flow.draft, day, flow.balances, income)
    return await show_main_menu(update, context, views.render_point_outcome(outcome, day))


async def _cancel_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await show_main_menu(update, context, "Point annulé : rien n'a été enregistré.")


async def remind_point(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rappel du 1er du mois, sauf si le point du mois clôturé est déjà fait."""
    job = context.job
    if job is None or job.chat_id is None:
        return
    day = today()
    if await asyncio.to_thread(is_point_done, day):
        return
    upcoming = await asyncio.to_thread(upcoming_charges, day)
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=views.render_point_reminder(closed_month(day), upcoming),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.MAIN,
    )
