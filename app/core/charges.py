from app.core.database import supabase


def insert_charge(name: str, amount: float, frequency: str, account_name: str | None = None) -> None:
    row = {"name": name, "amount": amount, "frequency": frequency}
    if account_name is not None:
        row["account_name"] = account_name
    supabase.table("charges").insert(row).execute()


def get_charges() -> list:
    result = supabase.table("charges").select("id, name, amount, frequency, account_name").order("name").execute()
    return result.data
