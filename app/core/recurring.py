"""Charges et revenus fixes : même structure (nom, montant, fréquence), tables distinctes.

Seules les charges ont un mois d'échéance (pour leurs paiements annuels).
Purement informatif : rien ici ne touche au solde des comptes.
"""

from decimal import Decimal

from app.core.database import supabase
from app.core.models import Change, Frequency, RecurringItem
from app.core.rows import Row, as_decimal, as_int, as_str
from app.core.tables import delete_by_id, name_exists

_COLUMNS = "id, name, amount, frequency"
_MAX_ROWS = 100


def _due_month(row: Row) -> int | None:
    value = row.get("due_month")
    return None if value is None else as_int(value)


def _to_item(row: Row) -> RecurringItem:
    return RecurringItem(
        id=as_int(row["id"]),
        name=as_str(row["name"]),
        amount=as_decimal(row["amount"]),
        frequency=Frequency(as_str(row["frequency"])),
        due_month=_due_month(row),
    )


class RecurringRepository:
    def __init__(self, table: str, *, with_due_month: bool) -> None:
        self._table = table
        self._columns = f"{_COLUMNS}, due_month" if with_due_month else _COLUMNS

    def all(self) -> list[RecurringItem]:
        rows: list[Row] = (
            supabase.table(self._table).select(self._columns).order("name").limit(_MAX_ROWS).execute().data
        )
        return [_to_item(row) for row in rows]

    def name_exists(self, name: str) -> bool:
        return name_exists(self._table, name)

    def create(self, name: str, amount: Decimal, frequency: Frequency, due_month: int | None = None) -> RecurringItem:
        row: Row = {"name": name, "amount": str(amount), "frequency": frequency.value}
        if due_month is not None:
            row["due_month"] = due_month
        rows: list[Row] = supabase.table(self._table).insert(row).execute().data
        return _to_item(rows[0])

    def set_amount(self, item_id: int, amount: Decimal) -> Change | None:
        current = self._get(item_id)
        if current is None:
            return None
        rows: list[Row] = supabase.table(self._table).update({"amount": str(amount)}).eq("id", item_id).execute().data
        if not rows:
            return None
        return Change(name=current.name, before=current.amount, after=amount)

    def set_due_month(self, item_id: int, due_month: int | None) -> bool:
        rows: list[Row] = supabase.table(self._table).update({"due_month": due_month}).eq("id", item_id).execute().data
        return bool(rows)

    def delete(self, item_id: int) -> bool:
        return delete_by_id(self._table, item_id)

    def _get(self, item_id: int) -> RecurringItem | None:
        rows: list[Row] = supabase.table(self._table).select(self._columns).eq("id", item_id).limit(1).execute().data
        return _to_item(rows[0]) if rows else None


charges = RecurringRepository("charges", with_due_month=True)
fixed_incomes = RecurringRepository("fixed_incomes", with_due_month=False)
