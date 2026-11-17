"""Épargne : rythme réel, projection, matelas de sécurité et objectifs.

Les objectifs se partagent l'épargne totale (comptes de type épargne), sans saisie de répartition :
elle remplit d'abord les objectifs sans date (une réserve, comme le matelas de sécurité), puis les
autres par date d'échéance. Le rythme est mesuré sur les derniers points du mois, pas supposé.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from app.core.models import ZERO, Checkpoint, add_months, month_diff

PACE_WINDOW = 4  # 4 points = 3 mois de rythme mesuré


@dataclass(frozen=True)
class SavingsGoal:
    id: int
    name: str
    amount: Decimal
    deadline: date | None  # premier jour du mois visé


@dataclass(frozen=True)
class GoalStatus:
    goal: SavingsGoal
    funded: Decimal  # part de l'épargne actuelle qui revient à cet objectif
    required_per_month: Decimal | None
    eta: date | None
    overdue: bool

    @property
    def gap(self) -> Decimal:
        return self.goal.amount - self.funded

    @property
    def reached(self) -> bool:
        return self.gap <= 0

    @property
    def on_track(self) -> bool | None:
        if self.reached:
            return True
        if self.goal.deadline is None or self.eta is None:
            return None
        return self.eta <= self.goal.deadline


@dataclass(frozen=True)
class SavingsPlan:
    savings_balance: Decimal
    has_savings_accounts: bool
    monthly_pace: Decimal | None
    pace_months: int
    savings_target: Decimal
    monthly_incomes: Decimal
    monthly_charges: Decimal
    goals: tuple[GoalStatus, ...]

    @property
    def living_budget(self) -> Decimal:
        return self.monthly_incomes - self.monthly_charges - self.savings_target

    @property
    def monthly_expenses(self) -> Decimal:
        """Dépenses prévues d'un mois : charges + budget de vie courante."""
        return self.monthly_charges + max(self.living_budget, ZERO)

    @property
    def coverage_months(self) -> Decimal | None:
        """Nombre de mois de dépenses que l'épargne couvrirait sans aucun revenu."""
        if self.monthly_expenses <= 0:
            return None
        return self.savings_balance / self.monthly_expenses

    def projection(self, months: int) -> Decimal | None:
        if self.monthly_pace is None:
            return None
        return self.savings_balance + self.monthly_pace * months


def savings_pace(history: list[Checkpoint]) -> tuple[Decimal | None, int]:
    """Évolution mensuelle moyenne de l'épargne entre le plus ancien et le plus récent relevé."""
    measured = sorted((c for c in history if c.savings_balance is not None), key=lambda c: c.month)
    if len(measured) < 2:
        return None, 0
    oldest, latest = measured[0], measured[-1]
    months = max(1, month_diff(oldest.month, latest.month))
    if oldest.savings_balance is None or latest.savings_balance is None:
        return None, 0
    return (latest.savings_balance - oldest.savings_balance) / months, months


def _priority(goal: SavingsGoal) -> tuple[int, date, int]:
    return (0, date.min, goal.id) if goal.deadline is None else (1, goal.deadline, goal.id)


def build_plan(
    *,
    savings_balance: Decimal,
    has_savings_accounts: bool,
    history: list[Checkpoint],
    savings_target: Decimal,
    monthly_incomes: Decimal,
    monthly_charges: Decimal,
    goals: list[SavingsGoal],
    current_month: date,
) -> SavingsPlan:
    pace, pace_months = savings_pace(history)
    remaining = max(savings_balance, ZERO)
    needed = ZERO
    statuses: list[GoalStatus] = []
    for goal in sorted(goals, key=_priority):
        funded = min(remaining, goal.amount)
        remaining -= funded
        # L'épargne doit couvrir cet objectif ET ceux qui passent avant lui.
        needed += goal.amount
        missing = needed - savings_balance
        required: Decimal | None = None
        eta: date | None = None
        overdue = False
        if missing > 0:
            if goal.deadline is not None:
                months_left = month_diff(current_month, goal.deadline)
                overdue = months_left <= 0
                required = None if overdue else missing / months_left
            if pace is not None and pace > 0:
                eta = add_months(current_month, int((missing / pace).to_integral_value(rounding=ROUND_CEILING)))
        statuses.append(GoalStatus(goal, funded, required, eta, overdue))
    return SavingsPlan(
        savings_balance=savings_balance,
        has_savings_accounts=has_savings_accounts,
        monthly_pace=pace,
        pace_months=pace_months,
        savings_target=savings_target,
        monthly_incomes=monthly_incomes,
        monthly_charges=monthly_charges,
        goals=tuple(statuses),
    )
