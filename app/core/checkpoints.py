"""Points mensuels : un relevé par mois clôturé, refaire le point du même mois le remplace."""

from datetime import date
from decimal import Decimal

from app.core.database import supabase
from app.core.models import Checkpoint, to_cents
from app.core.rows import Row, as_date, as_decimal, as_optional_decimal

_TABLE = "checkpoints"
_COLUMNS = (
    "month, taken_on, total_balance, income, fixed_incomes, charges, savings_target, "
    "savings_balance, charges_due, provisions"
)


def _to_checkpoint(row: Row) -> Checkpoint:
    return Checkpoint(
        month=as_date(row["month"]),
        taken_on=as_date(row["taken_on"]),
        total_balance=as_decimal(row["total_balance"]),
        income=as_decimal(row["income"]),
        fixed_incomes=as_decimal(row["fixed_incomes"]),
        charges=as_decimal(row["charges"]),
        savings_target=as_decimal(row["savings_target"]),
        savings_balance=as_optional_decimal(row["savings_balance"]),
        charges_due=as_optional_decimal(row["charges_due"]),
        provisions=as_optional_decimal(row["provisions"]),
    )


class CheckpointRepository:
    def recent(self, limit: int) -> list[Checkpoint]:
        """Les `limit` derniers relevés, du plus récent au plus ancien."""
        rows: list[Row] = supabase.table(_TABLE).select(_COLUMNS).order("month", desc=True).limit(limit).execute().data
        return [_to_checkpoint(row) for row in rows]

    def latest(self) -> Checkpoint | None:
        recent = self.recent(1)
        return recent[0] if recent else None

    def latest_before(self, month: date) -> Checkpoint | None:
        rows: list[Row] = (
            supabase.table(_TABLE)
            .select(_COLUMNS)
            .lt("month", month.isoformat())
            .order("month", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return _to_checkpoint(rows[0]) if rows else None

    def exists(self, month: date) -> bool:
        rows: list[Row] = supabase.table(_TABLE).select("month").eq("month", month.isoformat()).limit(1).execute().data
        return bool(rows)

    def record(
        self,
        *,
        month: date,
        taken_on: date,
        balances: dict[int, Decimal],
        income: Decimal,
        fixed_incomes: Decimal,
        charges: Decimal,
        charges_due: Decimal,
        provisions: Decimal,
        savings_target: Decimal,
    ) -> Checkpoint:
        """Met à jour tous les soldes et enregistre le point en une seule transaction (fonction SQL)."""
        data: Row | list[Row] = (
            supabase.rpc(
                "record_checkpoint",
                {
                    "p_month": month.isoformat(),
                    "p_taken_on": taken_on.isoformat(),
                    "p_income": str(to_cents(income)),
                    "p_fixed_incomes": str(to_cents(fixed_incomes)),
                    "p_charges": str(to_cents(charges)),
                    "p_charges_due": str(to_cents(charges_due)),
                    "p_provisions": str(to_cents(provisions)),
                    "p_savings_target": str(to_cents(savings_target)),
                    "p_balances": [
                        {"id": account_id, "balance": str(balance)} for account_id, balance in balances.items()
                    ],
                },
            )
            .execute()
            .data
        )
        # PostgREST renvoie un objet pour une fonction qui retourne une seule ligne.
        return _to_checkpoint(data[0] if isinstance(data, list) else data)


checkpoints = CheckpointRepository()
