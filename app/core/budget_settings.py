"""Réglages du budget : une seule ligne (id = 1), créée par la migration."""

from decimal import Decimal

from app.core.database import supabase
from app.core.models import ZERO
from app.core.rows import Row, as_decimal

_TABLE = "budget_settings"
_ROW_ID = 1


class BudgetSettingsRepository:
    def savings_target(self) -> Decimal:
        rows: list[Row] = supabase.table(_TABLE).select("savings_target").eq("id", _ROW_ID).limit(1).execute().data
        return as_decimal(rows[0]["savings_target"]) if rows else ZERO

    def set_savings_target(self, amount: Decimal) -> None:
        supabase.table(_TABLE).upsert({"id": _ROW_ID, "savings_target": str(amount)}).execute()


budget_settings = BudgetSettingsRepository()
