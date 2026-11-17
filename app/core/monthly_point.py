"""Point du mois : relever tous les soldes, puis en déduire dépenses et épargne."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.accounts import accounts
from app.core.budget_settings import budget_settings
from app.core.checkpoints import checkpoints
from app.core.models import (
    Account,
    Checkpoint,
    Frequency,
    MonthReview,
    RecurringItem,
    add_months,
    charges_due,
    closed_month,
    month_diff,
    monthly_total,
    provisions,
    upcoming_due,
)
from app.core.recurring import charges, fixed_incomes

UPCOMING_MONTHS = 2  # le mois qui commence et le suivant


@dataclass(frozen=True)
class PointDraft:
    """Tout ce qu'il faut pour mener le point, chargé en une fois au début."""

    month: date
    accounts: tuple[Account, ...]
    previous: Checkpoint | None
    replacing: bool
    monthly_fixed_incomes: Decimal
    charges: tuple[RecurringItem, ...]
    savings_target: Decimal

    @property
    def covered_months(self) -> list[date]:
        """Mois couverts depuis le point précédent (plusieurs si des points ont été sautés)."""
        if self.previous is None:
            return []
        return [add_months(self.previous.month, i) for i in range(1, month_diff(self.previous.month, self.month) + 1)]

    @property
    def months(self) -> int:
        return max(1, len(self.covered_months))

    @property
    def expected_income(self) -> Decimal:
        return self.monthly_fixed_incomes * self.months

    @property
    def monthly_charges(self) -> Decimal:
        return monthly_total(self.charges)


@dataclass(frozen=True)
class PointOutcome:
    checkpoint: Checkpoint
    review: MonthReview | None
    replaced: bool
    upcoming: list[tuple[date, RecurringItem]]
    has_undated_yearly: bool


def prepare_point(day: date) -> PointDraft:
    month = closed_month(day)
    # Lectures indépendantes : en parallèle pour ne pas cumuler les latences réseau.
    with ThreadPoolExecutor(max_workers=6) as pool:
        accounts_future = pool.submit(accounts.all)
        previous_future = pool.submit(checkpoints.latest_before, month)
        existing_future = pool.submit(checkpoints.exists, month)
        incomes_future = pool.submit(fixed_incomes.all)
        charges_future = pool.submit(charges.all)
        target_future = pool.submit(budget_settings.savings_target)
        return PointDraft(
            month=month,
            accounts=tuple(accounts_future.result()),
            previous=previous_future.result(),
            replacing=existing_future.result(),
            monthly_fixed_incomes=monthly_total(incomes_future.result()),
            charges=tuple(charges_future.result()),
            savings_target=target_future.result(),
        )


def save_point(draft: PointDraft, day: date, balances: dict[int, Decimal], income: Decimal) -> PointOutcome:
    months = draft.covered_months
    checkpoint = checkpoints.record(
        month=draft.month,
        taken_on=day,
        balances=balances,
        income=income,
        fixed_incomes=draft.monthly_fixed_incomes,
        charges=draft.monthly_charges,
        charges_due=charges_due(draft.charges, months),
        provisions=provisions(draft.charges, months),
        savings_target=draft.savings_target,
    )
    review = MonthReview(previous=draft.previous, current=checkpoint) if draft.previous is not None else None
    return PointOutcome(
        checkpoint=checkpoint,
        review=review,
        replaced=draft.replacing,
        upcoming=upcoming_due(draft.charges, add_months(draft.month, 1), UPCOMING_MONTHS),
        has_undated_yearly=any(c.frequency is Frequency.YEARLY and c.due_month is None for c in draft.charges),
    )


def is_point_done(day: date) -> bool:
    return checkpoints.exists(closed_month(day))


def upcoming_charges(day: date) -> list[tuple[date, RecurringItem]]:
    return upcoming_due(charges.all(), add_months(closed_month(day), 1), UPCOMING_MONTHS)
