"""Comptes : soldes saisis à la main, avec mémoire du solde précédent pour calculer l'écart."""

from decimal import Decimal

from postgrest.exceptions import APIError

from app.core.clock import today
from app.core.database import supabase
from app.core.models import Account, AccountKind, Change, StillReferencedError
from app.core.rows import Row, as_decimal, as_int, as_optional_date, as_optional_decimal, as_str
from app.core.tables import delete_by_id, name_exists

_TABLE = "accounts"
_COLUMNS = "id, name, kind, balance, previous_balance, balance_updated_on"
_MAX_ROWS = 100
_FOREIGN_KEY_VIOLATION = "23503"


def _to_account(row: Row) -> Account:
    return Account(
        id=as_int(row["id"]),
        name=as_str(row["name"]),
        kind=AccountKind(as_str(row["kind"])),
        balance=as_decimal(row["balance"]),
        previous_balance=as_optional_decimal(row["previous_balance"]),
        updated_on=as_optional_date(row["balance_updated_on"]),
    )


class AccountRepository:
    def all(self) -> list[Account]:
        rows: list[Row] = supabase.table(_TABLE).select(_COLUMNS).order("name").limit(_MAX_ROWS).execute().data
        return [_to_account(row) for row in rows]

    def name_exists(self, name: str) -> bool:
        return name_exists(_TABLE, name)

    def create(self, name: str, balance: Decimal, kind: AccountKind) -> Account:
        rows: list[Row] = (
            supabase.table(_TABLE)
            .insert(
                {
                    "name": name,
                    "kind": kind.value,
                    # initial_balance garde le solde d'ouverture, balance évolue ensuite.
                    "initial_balance": str(balance),
                    "balance": str(balance),
                    "balance_updated_on": today().isoformat(),
                }
            )
            .execute()
            .data
        )
        return _to_account(rows[0])

    def set_kind(self, account_id: int, kind: AccountKind) -> bool:
        rows: list[Row] = supabase.table(_TABLE).update({"kind": kind.value}).eq("id", account_id).execute().data
        return bool(rows)

    def set_amount(self, account_id: int, balance: Decimal) -> Change | None:
        """Enregistre le nouveau solde et renvoie l'écart avec le solde précédent."""
        current = self._get(account_id)
        if current is None:
            return None
        rows: list[Row] = (
            supabase.table(_TABLE)
            .update(
                {
                    "balance": str(balance),
                    "previous_balance": str(current.balance),
                    "balance_updated_on": today().isoformat(),
                }
            )
            .eq("id", account_id)
            .execute()
            .data
        )
        if not rows:
            return None
        return Change(
            name=current.name,
            before=current.balance,
            after=balance,
            previous_date=current.updated_on,
        )

    def delete(self, account_id: int) -> bool:
        try:
            return delete_by_id(_TABLE, account_id)
        except APIError as error:
            # Les anciennes dépenses/revenus (fonctionnalités retirées) pointent encore vers le compte.
            if error.code == _FOREIGN_KEY_VIOLATION:
                raise StillReferencedError(account_id) from error
            raise

    def _get(self, account_id: int) -> Account | None:
        rows: list[Row] = supabase.table(_TABLE).select(_COLUMNS).eq("id", account_id).limit(1).execute().data
        return _to_account(rows[0]) if rows else None


accounts = AccountRepository()
