"""Chargement des vues de synthèse : vue globale et épargne."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from app.core.accounts import accounts
from app.core.budget_settings import budget_settings
from app.core.checkpoints import checkpoints
from app.core.goals import goals
from app.core.models import AccountKind, Overview, first_of_month, monthly_total, total_balance
from app.core.recurring import charges, fixed_incomes
from app.core.savings import PACE_WINDOW, SavingsPlan, build_plan


def load_overview() -> Overview:
    # Lectures indépendantes : en parallèle pour ne pas cumuler les latences réseau.
    with ThreadPoolExecutor(max_workers=5) as pool:
        accounts_future = pool.submit(accounts.all)
        incomes_future = pool.submit(fixed_incomes.all)
        charges_future = pool.submit(charges.all)
        target_future = pool.submit(budget_settings.savings_target)
        checkpoint_future = pool.submit(checkpoints.latest)
        return Overview(
            accounts=tuple(accounts_future.result()),
            incomes=tuple(incomes_future.result()),
            charges=tuple(charges_future.result()),
            savings_target=target_future.result(),
            last_checkpoint=checkpoint_future.result(),
        )


def load_savings_plan(day: date) -> SavingsPlan:
    with ThreadPoolExecutor(max_workers=6) as pool:
        accounts_future = pool.submit(accounts.all)
        goals_future = pool.submit(goals.all)
        history_future = pool.submit(checkpoints.recent, PACE_WINDOW)
        incomes_future = pool.submit(fixed_incomes.all)
        charges_future = pool.submit(charges.all)
        target_future = pool.submit(budget_settings.savings_target)
        account_list = accounts_future.result()
        return build_plan(
            savings_balance=total_balance(account_list, AccountKind.SAVINGS),
            has_savings_accounts=any(a.kind is AccountKind.SAVINGS for a in account_list),
            history=history_future.result(),
            savings_target=target_future.result(),
            monthly_incomes=monthly_total(incomes_future.result()),
            monthly_charges=monthly_total(charges_future.result()),
            goals=goals_future.result(),
            current_month=first_of_month(day),
        )
