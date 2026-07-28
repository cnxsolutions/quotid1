from app.core.database import supabase


def get_accounts() -> list:
    rows = supabase.table("accounts").select("id, name, initial_balance, balance").order("name").execute().data
    result = []
    for a in rows:
        result.append({
            "id": a["id"],
            "name": a["name"],
            "balance": float(a.get("balance") or a["initial_balance"]),
        })
    return result


def get_account_id(name: str) -> int | None:
    result = supabase.table("accounts").select("id").ilike("name", name).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def get_default_account() -> str | None:
    result = supabase.table("accounts").select("name").order("name").limit(1).execute()
    return result.data[0]["name"] if result.data else None


def insert_account(name: str, balance: float = 0.0) -> None:
    supabase.table("accounts").insert({"name": name, "initial_balance": balance, "balance": balance}).execute()


def update_account_balance(account_id: int, delta: float) -> None:
    """Met à jour le solde d'un compte (positif = revenu, négatif = dépense)."""
    result = supabase.table("accounts").select("balance").eq("id", account_id).execute()
    if result.data:
        new_balance = float(result.data[0]["balance"] or 0) + delta
        supabase.table("accounts").update({"balance": new_balance}).eq("id", account_id).execute()
