"""Requêtes communes aux tables « nom unique + id » (comptes, charges, revenus, objectifs)."""

from app.core.database import supabase
from app.core.rows import Row


def name_exists(table: str, name: str) -> bool:
    rows: list[Row] = supabase.table(table).select("id").eq("name", name).limit(1).execute().data
    return bool(rows)


def delete_by_id(table: str, row_id: int) -> bool:
    rows: list[Row] = supabase.table(table).delete().eq("id", row_id).execute().data
    return bool(rows)
