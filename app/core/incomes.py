from datetime import date as Date
from app.core.database import supabase
from app.core.accounts import get_account_id, update_account_balance
from app.core.projects import get_project_id


def insert_income(amount: float, description: str = "", category: str | None = None, account_name: str | None = None, date: Date | None = None, project_name: str | None = None) -> bool | None:
    row = {"amount": amount, "description": description, "category": category}
    if date is not None:
        row["date"] = date.isoformat()
    if project_name is not None:
        project_id = get_project_id(project_name)
        if project_id is not None:
            row["project_id"] = project_id
    if account_name is not None:
        account_id = get_account_id(account_name)
        if account_id is None:
            return False
        row["account_id"] = account_id
        # Met à jour le solde du compte directement
        update_account_balance(account_id, amount)
    supabase.table("incomes").insert(row).execute()
    return True if account_name is not None else None


def get_recent_incomes(n: int = 5) -> list:
    return supabase.table("incomes").select("amount,category,date").order("date", desc=True).limit(n).execute().data
