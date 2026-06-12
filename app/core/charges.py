from datetime import date
from app.core.database import supabase


def insert_charge(name: str, amount: float, frequency: str, account_name: str | None = None) -> None:
    row = {"name": name, "amount": amount, "frequency": frequency}
    if account_name is not None:
        row["account_name"] = account_name
    supabase.table("charges").insert(row).execute()


def get_charges() -> list:
    result = supabase.table("charges").select("id, name, amount, frequency, account_name").order("name").execute()
    return result.data


def apply_monthly_charges(year: int, month: int) -> list[str]:
    charges = supabase.table("charges").select("id, name, amount, frequency, account_name").eq("frequency", "Mensuel").execute().data
    applied = []
    for c in charges:
        # idempotent : ignore si déjà logué ce mois
        existing = (
            supabase.table("charge_logs")
            .select("id")
            .eq("charge_id", c["id"])
            .eq("year", year)
            .eq("month", month)
            .execute()
            .data
        )
        if existing:
            continue
        # insérer dans expenses via la couche repository (résout account_name → account_id)
        from app.core.expenses import insert_expense
        insert_expense(
            float(c["amount"]),
            c["name"],
            "Abonnement",
            c["account_name"] or None,
            date(year, month, 1),
        )
        # marquer comme appliqué
        supabase.table("charge_logs").insert({
            "charge_id": c["id"],
            "year": year,
            "month": month,
        }).execute()
        applied.append(c["name"])
    return applied
