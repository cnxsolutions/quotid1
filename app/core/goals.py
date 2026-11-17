"""Objectifs d'épargne : un nom, un montant visé, une date facultative."""

from datetime import date
from decimal import Decimal

from app.core.database import supabase
from app.core.models import Change
from app.core.rows import Row, as_decimal, as_int, as_optional_date, as_str
from app.core.savings import SavingsGoal
from app.core.tables import delete_by_id, name_exists

_TABLE = "savings_goals"
_COLUMNS = "id, name, amount, deadline"
_MAX_ROWS = 50


def _to_goal(row: Row) -> SavingsGoal:
    return SavingsGoal(
        id=as_int(row["id"]),
        name=as_str(row["name"]),
        amount=as_decimal(row["amount"]),
        deadline=as_optional_date(row["deadline"]),
    )


class GoalRepository:
    def all(self) -> list[SavingsGoal]:
        rows: list[Row] = supabase.table(_TABLE).select(_COLUMNS).order("id").limit(_MAX_ROWS).execute().data
        return [_to_goal(row) for row in rows]

    def name_exists(self, name: str) -> bool:
        return name_exists(_TABLE, name)

    def create(self, name: str, amount: Decimal, deadline: date | None) -> SavingsGoal:
        row: Row = {"name": name, "amount": str(amount), "deadline": deadline.isoformat() if deadline else None}
        rows: list[Row] = supabase.table(_TABLE).insert(row).execute().data
        return _to_goal(rows[0])

    def set_amount(self, goal_id: int, amount: Decimal) -> Change | None:
        current = self._get(goal_id)
        if current is None:
            return None
        rows: list[Row] = supabase.table(_TABLE).update({"amount": str(amount)}).eq("id", goal_id).execute().data
        if not rows:
            return None
        return Change(name=current.name, before=current.amount, after=amount)

    def delete(self, goal_id: int) -> bool:
        return delete_by_id(_TABLE, goal_id)

    def _get(self, goal_id: int) -> SavingsGoal | None:
        rows: list[Row] = supabase.table(_TABLE).select(_COLUMNS).eq("id", goal_id).limit(1).execute().data
        return _to_goal(rows[0]) if rows else None


goals = GoalRepository()
