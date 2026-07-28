"""
Resync les soldes des comptes depuis l'historique des transactions.
Exécute: python -m migrations.resync_balances
"""
from app.core.database import supabase


def resync_balances():
    print("Resync des soldes depuis l'historique...\n")

    accounts = supabase.table("accounts").select("id, name, initial_balance").execute().data

    for acc in accounts:
        acc_id = acc["id"]
        name = acc["name"]
        initial = float(acc["initial_balance"] or 0)

        # Somme des revenus
        incomes = supabase.table("incomes").select("amount").eq("account_id", acc_id).execute().data
        total_in = sum(float(r["amount"]) for r in incomes)

        # Somme des dépenses
        expenses = supabase.table("expenses").select("amount").eq("account_id", acc_id).execute().data
        total_out = sum(float(r["amount"]) for r in expenses)

        # Calculer le solde réel
        real_balance = initial + total_in - total_out

        # Mettre à jour
        supabase.table("accounts").update({"balance": real_balance}).eq("id", acc_id).execute()

        print(f"{name}: {real_balance:.2f} € (init={initial}, +{total_in:.2f}, -{total_out:.2f})")

    print("\nDone !")


if __name__ == "__main__":
    resync_balances()
