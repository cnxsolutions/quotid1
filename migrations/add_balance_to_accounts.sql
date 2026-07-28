-- Migration: Ajouter colonne balance à accounts
-- Exécute ce SQL dans ton dashboard Supabase (SQL Editor)

-- 1. Ajouter la colonne balance
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS balance DECIMAL(12,2);

-- 2. Initialiser balance avec initial_balance pour tous les comptes existants
UPDATE accounts SET balance = initial_balance WHERE balance IS NULL;

-- 3. Optionnel : ajouter une valeur par défaut
ALTER TABLE accounts ALTER COLUMN balance SET DEFAULT 0;

-- Vérification
SELECT id, name, initial_balance, balance FROM accounts;
