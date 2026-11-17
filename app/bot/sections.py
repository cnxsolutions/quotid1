"""Parcours des sections Comptes, Charges, Revenus fixes et Épargne.

Les sections partagent le même parcours (ajouter, modifier le montant, supprimer) ; seule la
configuration `Section` change. Dernière étape d'un ajout : le type pour un compte, la fréquence
(puis l'échéance si elle est annuelle) pour une charge, la fréquence pour un revenu, la date pour
un objectif. Rien n'est enregistré avant la dernière étape.
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot import views
from app.bot.common import State, bold, get_flow, reply, set_flow, show_main_menu, text_of
from app.bot.money import format_eur, parse_amount
from app.bot.months import MONTH_NAMES, parse_future_month
from app.core.accounts import AccountRepository, accounts
from app.core.budget_settings import budget_settings
from app.core.clock import today
from app.core.goals import GoalRepository, goals
from app.core.models import Frequency, StillReferencedError, add_months, first_of_month
from app.core.overview import load_savings_plan
from app.core.recurring import RecurringRepository, charges, fixed_incomes

Repository = AccountRepository | RecurringRepository | GoalRepository

_NAME_MAX_LENGTH = 40
_NOT_FOUND = "❌ Élément introuvable : il a peut-être été supprimé."


@dataclass(frozen=True)
class Section:
    title: str
    update_button: str
    update_verb: str
    which: str
    name_prompt: str
    amount_prompt: str
    update_prompt: str
    amount_error: str
    empty_text: str
    positive_only: bool
    repo: Repository
    extra_buttons: tuple[str, ...] = ()
    asks_due_month: bool = False

    @property
    def menu(self) -> ReplyKeyboardMarkup:
        return kb.section_menu(self.update_button, self.extra_buttons)


ACCOUNTS = Section(
    title="🏦 Comptes",
    update_button=kb.BTN_UPDATE_BALANCE,
    update_verb="mettre à jour",
    which="Quel compte",
    name_prompt="🏦 Nom du nouveau compte ? (ex : Courant, Livret A)",
    amount_prompt="💶 Solde actuel ? (ex : 1250,50 ou -80)",
    update_prompt="💶 Nouveau solde de {name} ?",
    amount_error="❌ Solde invalide. Exemples : 1250,50 · -80 · 0",
    empty_text=f"Aucun compte pour l'instant.\nAppuie sur « {kb.BTN_ADD} » pour créer le premier.",
    positive_only=False,
    repo=accounts,
    extra_buttons=(kb.BTN_SET_KIND,),
)

CHARGES = Section(
    title="📦 Charges",
    update_button=kb.BTN_EDIT,
    update_verb="modifier",
    which="Quelle charge",
    name_prompt="📦 Nom de la charge ? (ex : Loyer, Assurance auto)",
    amount_prompt="💶 Montant ?",
    update_prompt="💶 Nouveau montant de {name} ?",
    amount_error="❌ Montant invalide : un nombre positif, ex. 49,99",
    empty_text=f"Aucune charge pour l'instant.\nAppuie sur « {kb.BTN_ADD} » pour en recenser une.",
    positive_only=True,
    repo=charges,
    extra_buttons=(kb.BTN_DUE_MONTH,),
    asks_due_month=True,
)

INCOMES = Section(
    title="💼 Revenus fixes",
    update_button=kb.BTN_EDIT,
    update_verb="modifier",
    which="Quel revenu",
    name_prompt="💼 Nom du revenu ? (ex : Salaire)",
    amount_prompt="💶 Montant ?",
    update_prompt="💶 Nouveau montant de {name} ?",
    amount_error="❌ Montant invalide : un nombre positif, ex. 2100",
    empty_text=(
        f"Aucun revenu fixe pour l'instant.\nAppuie sur « {kb.BTN_ADD} » pour en recenser un.\n"
        "<i>Informatif : ils n'alimentent pas tes comptes.</i>"
    ),
    positive_only=True,
    repo=fixed_incomes,
)

SAVINGS = Section(
    title="🎯 Épargne",
    update_button=kb.BTN_EDIT,
    update_verb="modifier",
    which="Quel objectif",
    name_prompt="🎯 Nom de l'objectif ? (ex : Voyage, Matelas de sécurité)",
    amount_prompt="💶 Montant à atteindre ?",
    update_prompt="💶 Nouveau montant à atteindre pour {name} ?",
    amount_error="❌ Montant invalide : un nombre positif, ex. 3000",
    empty_text=f"Aucun objectif pour l'instant.\nAppuie sur « {kb.BTN_ADD} » pour en créer un.",
    positive_only=True,
    repo=goals,
    extra_buttons=(kb.BTN_MONTHLY_TARGET,),
)


class Action(Enum):
    ADD = auto()
    UPDATE = auto()
    DELETE = auto()
    SET_KIND = auto()
    SET_DUE_MONTH = auto()
    SET_TARGET = auto()


_PICK_ACTIONS = {kb.BTN_SET_KIND: Action.SET_KIND, kb.BTN_DUE_MONTH: Action.SET_DUE_MONTH}


@dataclass
class Flow:
    section: Section
    action: Action | None = None
    choices: dict[str, int] = field(default_factory=dict)
    target_id: int | None = None
    target_name: str = ""
    new_name: str = ""
    new_amount: Decimal | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _target_id(flow: Flow) -> int:
    if flow.target_id is None:
        raise RuntimeError("Aucun élément sélectionné")
    return flow.target_id


def _new_amount(flow: Flow) -> Decimal:
    if flow.new_amount is None:
        raise RuntimeError("Montant absent à la dernière étape d'un ajout")
    return flow.new_amount


def _clean_name(raw: str) -> str:
    return " ".join(raw.split())


def _name_error(name: str) -> str | None:
    if not name:
        return "❌ Le nom ne peut pas être vide."
    if len(name) > _NAME_MAX_LENGTH:
        return f"❌ {_NAME_MAX_LENGTH} caractères maximum."
    if name in kb.RESERVED_LABELS:
        return "❌ Ce nom est celui d'un bouton, choisis-en un autre."
    return None


def _load_choices(repo: Repository, action: Action) -> dict[str, int]:
    # Nom affiché sur le bouton → identifiant : les noms sont uniques dans chaque section.
    if action is Action.SET_DUE_MONTH and isinstance(repo, RecurringRepository):
        return {item.name: item.id for item in repo.all() if item.frequency is Frequency.YEARLY}
    return {entry.name: entry.id for entry in repo.all()}


async def _render_section(section: Section) -> str:
    repo = section.repo
    if isinstance(repo, AccountRepository):
        account_list = await asyncio.to_thread(repo.all)
        return views.render_accounts(section.title, account_list, section.empty_text, today())
    if isinstance(repo, RecurringRepository):
        items = await asyncio.to_thread(repo.all)
        return views.render_recurring(section.title, items, section.empty_text)
    plan = await asyncio.to_thread(load_savings_plan, today())
    return views.render_savings(plan)


async def _show_section(
    update: Update, context: ContextTypes.DEFAULT_TYPE, section: Section, notice: str | None = None
) -> int:
    set_flow(context, Flow(section))
    text = await _render_section(section)
    if notice is not None:
        text = f"{notice}\n\n{text}"
    await reply(update, text, section.menu)
    return State.MENU


async def _created(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: Flow) -> int:
    return await _show_section(update, context, flow.section, f"✅ Ajouté : {bold(flow.new_name)}")


# ── Entrées ──────────────────────────────────────────────────────────────────


async def open_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_section(update, context, ACCOUNTS)


async def open_charges(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_section(update, context, CHARGES)


async def open_incomes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_section(update, context, INCOMES)


async def open_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_section(update, context, SAVINGS)


# ── Menu de section ──────────────────────────────────────────────────────────


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    section = flow.section
    choice = text_of(update)
    if choice == kb.BTN_ADD:
        flow.action = Action.ADD
        await reply(update, section.name_prompt, kb.BACK)
        return State.NAME
    if choice == section.update_button:
        return await _ask_target(update, flow, Action.UPDATE)
    if choice == kb.BTN_DELETE:
        return await _ask_target(update, flow, Action.DELETE)
    if choice in section.extra_buttons and choice == kb.BTN_MONTHLY_TARGET:
        return await _ask_monthly_target(update, flow)
    if choice in section.extra_buttons and choice in _PICK_ACTIONS:
        return await _ask_target(update, flow, _PICK_ACTIONS[choice])
    if choice == kb.BTN_BACK:
        return await show_main_menu(update, context)
    await reply(update, "Choisis une action avec les boutons 👇", section.menu)
    return State.MENU


async def _ask_target(update: Update, flow: Flow, action: Action) -> int:
    section = flow.section
    choices = await asyncio.to_thread(_load_choices, section.repo, action)
    if not choices:
        empty = (
            "Aucune charge annuelle : l'échéance ne concerne que les charges annuelles."
            if action is Action.SET_DUE_MONTH
            else section.empty_text
        )
        await reply(update, empty, section.menu)
        return State.MENU
    flow.action = action
    flow.choices = choices
    questions = {
        Action.UPDATE: f"{section.which} {section.update_verb} ?",
        Action.DELETE: f"🗑 {section.which} supprimer ?",
        Action.SET_KIND: f"🏷 {section.which} classer (courant ou épargne) ?",
        Action.SET_DUE_MONTH: f"📅 {section.which} dater ?",
    }
    await reply(update, questions[action], kb.choices(flow.choices))
    return State.PICK


async def _ask_monthly_target(update: Update, flow: Flow) -> int:
    plan = await asyncio.to_thread(load_savings_plan, today())
    flow.action = Action.SET_TARGET
    await reply(update, views.render_target_prompt(plan.savings_target, plan.living_budget), kb.BACK)
    return State.TARGET


# ── Étapes ───────────────────────────────────────────────────────────────────


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    choice = text_of(update)
    if choice == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    target_id = flow.choices.get(choice)
    if target_id is None:
        await reply(update, "Choisis dans la liste 👇", kb.choices(flow.choices))
        return State.PICK
    flow.target_id = target_id
    flow.target_name = choice
    if flow.action is Action.DELETE:
        await reply(update, f"🗑 Supprimer {bold(choice)} ? C'est définitif.", kb.CONFIRM_DELETE)
        return State.CONFIRM_DELETE
    if flow.action is Action.SET_KIND:
        await reply(update, f"🏷 Type de {bold(choice)} ?", kb.KIND)
        return State.KIND
    if flow.action is Action.SET_DUE_MONTH:
        await reply(update, f"📅 Quel mois tombe {bold(choice)} ?", kb.DUE_MONTH)
        return State.DUE_MONTH
    await reply(update, flow.section.update_prompt.format(name=bold(choice)), kb.BACK)
    return State.AMOUNT


async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    raw = text_of(update)
    if raw == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    name = _clean_name(raw)
    error = _name_error(name)
    if error is None and await asyncio.to_thread(flow.section.repo.name_exists, name):
        error = "❌ Ce nom existe déjà, choisis-en un autre."
    if error is not None:
        await reply(update, error, kb.BACK)
        return State.NAME
    flow.new_name = name
    await reply(update, flow.section.amount_prompt, kb.BACK)
    return State.AMOUNT


async def on_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    section = flow.section
    raw = text_of(update)
    if raw == kb.BTN_BACK:
        return await _show_section(update, context, section)
    amount = parse_amount(raw)
    if amount is None or (section.positive_only and amount <= 0):
        await reply(update, section.amount_error, kb.BACK)
        return State.AMOUNT

    if flow.action is Action.UPDATE:
        change = await asyncio.to_thread(section.repo.set_amount, _target_id(flow), amount)
        notice = views.render_change(change, today()) if change is not None else _NOT_FOUND
        return await _show_section(update, context, section, notice)

    flow.new_amount = amount
    if isinstance(section.repo, AccountRepository):
        await reply(update, "🏷 Type de compte ?", kb.KIND)
        return State.KIND
    if isinstance(section.repo, GoalRepository):
        await reply(update, "📅 Pour quand ? Choisis, ou tape un mois (ex : 06/2027, juin 2027).", kb.DEADLINE)
        return State.DEADLINE
    await reply(update, "🔄 Fréquence ?", kb.FREQUENCY)
    return State.FREQUENCY


async def on_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    choice = text_of(update)
    if choice == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    kind = kb.KIND_BY_LABEL.get(choice)
    if kind is None:
        await reply(update, "Choisis un type avec les boutons 👇", kb.KIND)
        return State.KIND
    if flow.action is Action.SET_KIND:
        changed = await asyncio.to_thread(accounts.set_kind, _target_id(flow), kind)
        notice = f"✅ {bold(flow.target_name)} : {choice}" if changed else _NOT_FOUND
        return await _show_section(update, context, flow.section, notice)
    await asyncio.to_thread(accounts.create, flow.new_name, _new_amount(flow), kind)
    return await _created(update, context, flow)


async def on_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    raw = text_of(update)
    if raw == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    try:
        frequency = Frequency(raw)
    except ValueError:
        await reply(update, "Choisis une fréquence avec les boutons 👇", kb.FREQUENCY)
        return State.FREQUENCY
    if frequency is Frequency.YEARLY and flow.section.asks_due_month:
        await reply(update, "📅 Quel mois tombe-t-elle ? (pour te prévenir à l'avance)", kb.DUE_MONTH)
        return State.DUE_MONTH
    repo = flow.section.repo
    if not isinstance(repo, RecurringRepository):
        raise RuntimeError("Fréquence reçue hors d'une charge ou d'un revenu fixe")
    await asyncio.to_thread(repo.create, flow.new_name, _new_amount(flow), frequency)
    return await _created(update, context, flow)


async def on_due_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    choice = text_of(update)
    if choice == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    if choice == kb.BTN_UNKNOWN_MONTH:
        due_month: int | None = None
    elif choice in kb.DUE_MONTH_BY_LABEL:
        due_month = kb.DUE_MONTH_BY_LABEL[choice]
    else:
        await reply(update, "Choisis un mois avec les boutons 👇", kb.DUE_MONTH)
        return State.DUE_MONTH
    repo = flow.section.repo
    if not isinstance(repo, RecurringRepository):
        raise RuntimeError("Échéance reçue hors d'une charge")
    if flow.action is Action.SET_DUE_MONTH:
        changed = await asyncio.to_thread(repo.set_due_month, _target_id(flow), due_month)
        when = f"en {MONTH_NAMES[due_month - 1]}" if due_month is not None else "inconnue"
        notice = f"✅ {bold(flow.target_name)} : échéance {when}" if changed else _NOT_FOUND
        return await _show_section(update, context, flow.section, notice)
    await asyncio.to_thread(repo.create, flow.new_name, _new_amount(flow), Frequency.YEARLY, due_month)
    return await _created(update, context, flow)


async def on_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    choice = text_of(update)
    if choice == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    current_month = first_of_month(today())
    if choice == kb.BTN_NO_DEADLINE:
        deadline = None
    elif choice in kb.DEADLINE_OFFSETS:
        deadline = add_months(current_month, kb.DEADLINE_OFFSETS[choice])
    else:
        deadline = parse_future_month(choice, current_month)
        if deadline is None:
            await reply(update, "❌ Mois non reconnu ou déjà passé. Exemples : 06/2027 · juin 2027", kb.DEADLINE)
            return State.DEADLINE
    await asyncio.to_thread(goals.create, flow.new_name, _new_amount(flow), deadline)
    return await _created(update, context, flow)


async def on_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    raw = text_of(update)
    if raw == kb.BTN_BACK:
        return await _show_section(update, context, flow.section)
    amount = parse_amount(raw)
    if amount is None or amount < 0:
        await reply(update, "❌ Montant invalide : un nombre positif ou 0, ex. 300", kb.BACK)
        return State.TARGET
    await asyncio.to_thread(budget_settings.set_savings_target, amount)
    notice = f"✅ Épargne visée : <b>{format_eur(amount)}</b> / mois"
    return await _show_section(update, context, flow.section, notice)


async def on_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = get_flow(context, Flow)
    section = flow.section
    choice = text_of(update)
    if choice in (kb.BTN_KEEP, kb.BTN_BACK):
        return await _show_section(update, context, section, "Suppression annulée.")
    if choice != kb.BTN_CONFIRM_DELETE:
        await reply(update, "Réponds avec les boutons 👇", kb.CONFIRM_DELETE)
        return State.CONFIRM_DELETE
    name = bold(flow.target_name)
    try:
        deleted = await asyncio.to_thread(section.repo.delete, _target_id(flow))
    except StillReferencedError:
        notice = (
            f"❌ {name} est encore lié à d'anciennes dépenses ou revenus.\n"
            "Lance migrations/drop_legacy_tables.sql dans Supabase pour les effacer, puis réessaie."
        )
    else:
        notice = f"🗑 Supprimé : {name}" if deleted else _NOT_FOUND
    return await _show_section(update, context, section, notice)


def is_in_progress(flow: object) -> bool:
    return isinstance(flow, Flow) and flow.action is not None
