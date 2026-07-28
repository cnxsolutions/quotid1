from datetime import date as Date
from app.core.database import supabase
from app.core.accounts import get_account_id, update_account_balance


def insert_expense(amount: float, description: str = "", category: str | None = None, account_name: str | None = None, date: Date | None = None) -> bool | None:
    row = {"amount": amount, "description": description, "category": category}
    if date is not None:
        row["date"] = date.isoformat()
    if account_name is not None:
        account_id = get_account_id(account_name)
        if account_id is None:
            return False
        row["account_id"] = account_id
        # Met à jour le solde du compte directement
        update_account_balance(account_id, -amount)
    supabase.table("expenses").insert(row).execute()
    return True if account_name is not None else None


def get_recent_expenses(n: int = 5) -> list:
    return supabase.table("expenses").select("amount,category,date").order("date", desc=True).limit(n).execute().data
