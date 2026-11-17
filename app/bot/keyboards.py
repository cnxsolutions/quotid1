from collections.abc import Iterable

from telegram import ReplyKeyboardMarkup

from app.bot.months import MONTH_NAMES
from app.core.models import AccountKind, Frequency

BTN_POINT = "📍 Point du mois"
BTN_OVERVIEW = "📊 Vue globale"
BTN_ACCOUNTS = "🏦 Comptes"
BTN_CHARGES = "📦 Charges"
BTN_INCOMES = "💼 Revenus fixes"
BTN_SAVINGS = "🎯 Épargne"

BTN_ADD = "➕ Ajouter"
BTN_UPDATE_BALANCE = "🔄 Mettre à jour"
BTN_EDIT = "✏️ Modifier"
BTN_SET_KIND = "🏷 Type"
BTN_DUE_MONTH = "📅 Échéance"
BTN_MONTHLY_TARGET = "💶 Épargne / mois"
BTN_DELETE = "🗑 Supprimer"
BTN_BACK = "⬅️ Retour"
BTN_CONFIRM_DELETE = "✅ Oui, supprimer"
BTN_KEEP = "❌ Non, garder"

BTN_KIND_CURRENT = "💳 Courant"
BTN_KIND_SAVINGS = "🐷 Épargne"
KIND_BY_LABEL = {BTN_KIND_CURRENT: AccountKind.CURRENT, BTN_KIND_SAVINGS: AccountKind.SAVINGS}

BTN_UNCHANGED = "✅ Inchangé"
BTN_CANCEL_POINT = "❌ Annuler le point"

BTN_UNKNOWN_MONTH = "❔ Je ne sais pas"
DUE_MONTH_BY_LABEL = {name.capitalize(): number for number, name in enumerate(MONTH_NAMES, start=1)}

BTN_NO_DEADLINE = "Sans date"
DEADLINE_OFFSETS = {"Dans 6 mois": 6, "Dans 1 an": 12, "Dans 2 ans": 24}

FREQUENCY_LABELS = [frequency.value for frequency in Frequency]

# Un nom identique à un bouton serait intercepté par la navigation au lieu d'être sélectionné.
RESERVED_LABELS = frozenset(
    {
        BTN_POINT,
        BTN_OVERVIEW,
        BTN_ACCOUNTS,
        BTN_CHARGES,
        BTN_INCOMES,
        BTN_SAVINGS,
        BTN_ADD,
        BTN_UPDATE_BALANCE,
        BTN_EDIT,
        BTN_SET_KIND,
        BTN_DUE_MONTH,
        BTN_MONTHLY_TARGET,
        BTN_DELETE,
        BTN_BACK,
        BTN_CONFIRM_DELETE,
        BTN_KEEP,
        BTN_UNCHANGED,
        BTN_CANCEL_POINT,
        BTN_UNKNOWN_MONTH,
        BTN_NO_DEADLINE,
        *DEADLINE_OFFSETS,
        *KIND_BY_LABEL,
        *FREQUENCY_LABELS,
    }
)


def _keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


MAIN = _keyboard([[BTN_POINT, BTN_OVERVIEW], [BTN_ACCOUNTS, BTN_CHARGES], [BTN_INCOMES, BTN_SAVINGS]])
BACK = _keyboard([[BTN_BACK]])
CONFIRM_DELETE = _keyboard([[BTN_CONFIRM_DELETE, BTN_KEEP]])
FREQUENCY = _keyboard([FREQUENCY_LABELS, [BTN_BACK]])
KIND = _keyboard([list(KIND_BY_LABEL), [BTN_BACK]])
POINT_BALANCE = _keyboard([[BTN_UNCHANGED], [BTN_CANCEL_POINT]])
_MONTH_LABELS = list(DUE_MONTH_BY_LABEL)
DUE_MONTH = _keyboard([_MONTH_LABELS[i : i + 3] for i in range(0, 12, 3)] + [[BTN_UNKNOWN_MONTH], [BTN_BACK]])
DEADLINE = _keyboard([list(DEADLINE_OFFSETS), [BTN_NO_DEADLINE, BTN_BACK]])


def section_menu(update_button: str, extra_buttons: tuple[str, ...] = ()) -> ReplyKeyboardMarkup:
    if extra_buttons:
        return _keyboard([[update_button, BTN_ADD], [*extra_buttons, BTN_DELETE], [BTN_BACK]])
    return _keyboard([[update_button, BTN_ADD], [BTN_DELETE, BTN_BACK]])


def choices(names: Iterable[str]) -> ReplyKeyboardMarkup:
    return _keyboard([[name] for name in names] + [[BTN_BACK]])


def point_income(default_button: str | None) -> ReplyKeyboardMarkup:
    rows = [[default_button]] if default_button is not None else []
    return _keyboard([*rows, [BTN_CANCEL_POINT]])
