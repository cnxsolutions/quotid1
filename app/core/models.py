"""Entités et règles métier : comptes, charges, revenus fixes, points mensuels et budget.

Principe : l'utilisateur ne saisit jamais ses dépenses. Il relève ses soldes une fois par mois
(le « point ») et les dépenses s'en déduisent :
    dépensé = revenus reçus − évolution du total des comptes
Un virement entre deux comptes ne change pas le total : ce n'est donc pas une dépense.
Les charges et revenus fixes restent informatifs : ils ne modifient jamais un solde.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

ZERO = Decimal("0")
MONTHS_PER_YEAR = Decimal("12")
_CENT = Decimal("0.01")

# La paie tombe en fin de mois (le 30 ou le 31, avancée d'un ou deux jours si c'est un week-end) :
# un point fait entre le 26 du mois M et le 25 du mois M+1 clôture le mois M.
_PAYDAY_MARGIN_DAYS = 5


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


# ── Mois ─────────────────────────────────────────────────────────────────────
# Un mois est représenté par la date de son premier jour.


def first_of_month(day: date) -> date:
    return day.replace(day=1)


def add_months(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def month_diff(start: date, end: date) -> int:
    """Nombre de mois de `start` à `end` (négatif si `end` est avant)."""
    return (end.year - start.year) * 12 + end.month - start.month


def months_between(start: date, end: date) -> int:
    return max(1, month_diff(start, end))


def closed_month(day: date) -> date:
    """Mois clôturé par un point fait le `day`."""
    shifted = day + timedelta(days=_PAYDAY_MARGIN_DAYS)
    return add_months(first_of_month(shifted), -1)


def budget_month(day: date) -> date:
    """Mois de budget en cours : celui qui suit le dernier mois clôturé."""
    return add_months(closed_month(day), 1)


# ── Comptes, charges, revenus ────────────────────────────────────────────────


class Frequency(str, Enum):
    # Valeurs déjà stockées en base dans la table charges : ne pas les renommer.
    MONTHLY = "Mensuel"
    YEARLY = "Annuel"


class AccountKind(str, Enum):
    CURRENT = "courant"
    SAVINGS = "epargne"


class StillReferencedError(Exception):
    """L'élément est encore référencé par d'anciennes données et ne peut pas être supprimé."""


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    kind: AccountKind
    balance: Decimal
    previous_balance: Decimal | None
    updated_on: date | None

    @property
    def last_change(self) -> Decimal | None:
        if self.previous_balance is None:
            return None
        return self.balance - self.previous_balance


@dataclass(frozen=True)
class RecurringItem:
    id: int
    name: str
    amount: Decimal
    frequency: Frequency
    due_month: int | None = None  # 1 à 12, seulement pour une charge annuelle

    @property
    def monthly_amount(self) -> Decimal:
        if self.frequency is Frequency.YEARLY:
            return self.amount / MONTHS_PER_YEAR
        return self.amount

    @property
    def is_dated_yearly(self) -> bool:
        return self.frequency is Frequency.YEARLY and self.due_month is not None


def monthly_total(items: tuple[RecurringItem, ...] | list[RecurringItem]) -> Decimal:
    return sum((item.monthly_amount for item in items), ZERO)


def total_balance(accounts: tuple[Account, ...] | list[Account], kind: AccountKind | None = None) -> Decimal:
    return sum((a.balance for a in accounts if kind is None or a.kind is kind), ZERO)


def charges_due(items: tuple[RecurringItem, ...] | list[RecurringItem], months: list[date]) -> Decimal:
    """Charges réellement dues sur ces mois : une charge annuelle datée tombe en entier son mois-là.

    Une charge annuelle sans mois d'échéance reste lissée (1/12 par mois), faute de mieux.
    """
    total = ZERO
    for item in items:
        if item.is_dated_yearly:
            total += item.amount * sum(1 for month in months if month.month == item.due_month)
        else:
            total += item.monthly_amount * len(months)
    return total


def provisions(items: tuple[RecurringItem, ...] | list[RecurringItem], months: list[date]) -> Decimal:
    """Part des charges annuelles à mettre de côté sur ces mois (négative le mois d'une échéance)."""
    return monthly_total(items) * len(months) - charges_due(items, months)


def upcoming_due(
    items: tuple[RecurringItem, ...] | list[RecurringItem], start: date, count: int
) -> list[tuple[date, RecurringItem]]:
    """Charges annuelles qui tombent dans les `count` mois à partir de `start`."""
    due: list[tuple[date, RecurringItem]] = []
    for offset in range(count):
        month = add_months(start, offset)
        due += [(month, item) for item in items if item.is_dated_yearly and item.due_month == month.month]
    return due


@dataclass(frozen=True)
class Change:
    """Passage d'un montant à un autre lors d'une mise à jour manuelle."""

    name: str
    before: Decimal
    after: Decimal
    previous_date: date | None = None

    @property
    def delta(self) -> Decimal:
        return self.after - self.before


# ── Points mensuels ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Checkpoint:
    """Relevé mensuel : soldes et instantané du budget prévu à cette date.

    Les trois derniers champs sont vides pour les relevés antérieurs à leur création.
    """

    month: date
    taken_on: date
    total_balance: Decimal
    income: Decimal
    fixed_incomes: Decimal
    charges: Decimal
    savings_target: Decimal
    savings_balance: Decimal | None = None
    charges_due: Decimal | None = None
    provisions: Decimal | None = None


@dataclass(frozen=True)
class MonthReview:
    """Bilan entre deux points consécutifs (plusieurs mois si des points ont été sautés)."""

    previous: Checkpoint
    current: Checkpoint

    @property
    def months(self) -> int:
        return months_between(self.previous.month, self.current.month)

    @property
    def saved(self) -> Decimal:
        return self.current.total_balance - self.previous.total_balance

    @property
    def provisions(self) -> Decimal:
        return self.current.provisions if self.current.provisions is not None else ZERO

    @property
    def net_saved(self) -> Decimal:
        """Épargne hors provisions : l'argent mis de côté pour une charge annuelle n'est pas libre."""
        return self.saved - self.provisions

    @property
    def spent(self) -> Decimal:
        return self.current.income - self.saved

    @property
    def charges(self) -> Decimal:
        if self.current.charges_due is not None:
            return self.current.charges_due
        return self.current.charges * self.months

    @property
    def living(self) -> Decimal:
        """Dépenses de vie courante : tout ce qui n'est pas une charge."""
        return self.spent - self.charges

    @property
    def living_budget(self) -> Decimal:
        current = self.current
        return (current.fixed_incomes - current.charges - current.savings_target) * self.months

    @property
    def savings_goal(self) -> Decimal:
        return self.current.savings_target * self.months


# ── Vue globale ──────────────────────────────────────────────────────────────


class ProgressStatus(Enum):
    NO_POINT = "no_point"
    POINT_DUE = "point_due"
    STALE = "stale"
    TRACKED = "tracked"


@dataclass(frozen=True)
class MonthProgress:
    """Où en est le mois en cours depuis le dernier point."""

    status: ProgressStatus
    since: Checkpoint | None = None
    due_month: date | None = None
    spent: Decimal = ZERO
    remaining: Decimal = ZERO


@dataclass(frozen=True)
class Overview:
    accounts: tuple[Account, ...]
    incomes: tuple[RecurringItem, ...]
    charges: tuple[RecurringItem, ...]
    savings_target: Decimal
    last_checkpoint: Checkpoint | None

    @property
    def is_empty(self) -> bool:
        return not (self.accounts or self.incomes or self.charges)

    @property
    def total_balance(self) -> Decimal:
        return total_balance(self.accounts)

    @property
    def monthly_incomes(self) -> Decimal:
        return monthly_total(self.incomes)

    @property
    def monthly_charges(self) -> Decimal:
        return monthly_total(self.charges)

    @property
    def living_budget(self) -> Decimal:
        return self.monthly_incomes - self.monthly_charges - self.savings_target

    def upcoming(self, today: date, count: int = 3) -> list[tuple[date, RecurringItem]]:
        return upcoming_due(self.charges, budget_month(today), count)

    def progress(self, today: date) -> MonthProgress:
        last = self.last_checkpoint
        if last is None:
            return MonthProgress(ProgressStatus.NO_POINT)
        due = closed_month(today)
        if due > last.month:
            # La paie est tombée : tant que le point n'est pas fait, l'estimation serait fausse.
            return MonthProgress(ProgressStatus.POINT_DUE, since=last, due_month=due)
        if not any(a.updated_on is not None and a.updated_on > last.taken_on for a in self.accounts):
            return MonthProgress(ProgressStatus.STALE, since=last)
        # Aucun revenu attendu avant la prochaine paie : toute baisse du total est une dépense.
        spent = last.total_balance - self.total_balance
        envelope = self.monthly_incomes - self.savings_target
        return MonthProgress(ProgressStatus.TRACKED, since=last, spent=spent, remaining=envelope - spent)
