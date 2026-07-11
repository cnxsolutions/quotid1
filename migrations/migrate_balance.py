"""
Script de migration pour ajouter la colonne balance à accounts.
Exécute: python migrations/migrate_balance.py
"""
from app.core.database import supabase

def migrate():
    print("Migration: Ajout de la colonne 'balance' à la table 'accounts'...")

    # Vérifier si la colonne existe déjà
    try:
        supabase.table("accounts").select("balance").limit(1).execute()
        print("La colonne 'balance' existe déjà.")
        return
    except Exception:
        pass

    # Exécuter le SQL directement via Supabase
    # Note: Tu dois exécuter ces commandes dans le SQL Editor de Supabase:
    # 1. ALTER TABLE accounts ADD COLUMN balance DECIMAL(12,2);
    # 2. UPDATE accounts SET balance = initial_balance WHERE balance IS NULL;

    print("\nVa dans Supabase > SQL Editor et exécute:")
    print("""
ALTER TABLE accounts ADD COLUMN balance DECIMAL(12,2);
UPDATE accounts SET balance = initial_balance WHERE balance IS NULL;
ALTER TABLE accounts ALTER COLUMN balance SET DEFAULT 0;
SELECT id, name, initial_balance, balance FROM accounts;
""")

if __name__ == "__main__":
    migrate()
