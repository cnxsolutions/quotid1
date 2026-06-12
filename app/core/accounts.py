from app.core.database import supabase


def get_accounts() -> list:
    rows = supabase.table("accounts").select("id, name, initial_balance").order("name").execute().data
    result = []
    for a in rows:
        inc = sum(
            float(r["amount"])
            for r in supabase.table("incomes").select("amount").eq("account_id", a["id"]).execute().data
        )
        exp = sum(
            float(r["amount"])
            for r in supabase.table("expenses").select("amount").eq("account_id", a["id"]).execute().data
        )
        result.append({
            "id": a["id"],
            "name": a["name"],
            "balance": float(a["initial_balance"]) + inc - exp,
        })
    return result


def get_account_id(name: str) -> int | None:
    result = supabase.table("accounts").select("id").ilike("name", name).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def get_default_account() -> str | None:
    result = supabase.table("accounts").select("name").order("name").limit(1).execute()
    return result.data[0]["name"] if result.data else None


def insert_account(name: str, balance: float = 0.0) -> None:
    supabase.table("accounts").insert({"name": name, "initial_balance": balance}).execute()
