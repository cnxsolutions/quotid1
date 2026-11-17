-- Point du mois : type de compte (courant / épargne), objectif d'épargne, relevés mensuels.
-- À exécuter dans Supabase > SQL Editor APRÈS 2026_11_comptes_charges_revenus_fixes.sql,
-- et avant de relancer le bot. Idempotent : peut être rejoué sans risque.

-- 1. Type de compte. Les comptes existants deviennent « courant » : reclasse ton épargne
--    depuis le bot (🏦 Comptes → 🏷 Type).
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'courant' CHECK (kind IN ('courant', 'epargne'));

-- 2. Réglages du budget : une seule ligne.
CREATE TABLE IF NOT EXISTS budget_settings (
    id             smallint      PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    savings_target numeric(12,2) NOT NULL DEFAULT 0 CHECK (savings_target >= 0)
);
INSERT INTO budget_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 3. Relevés mensuels : un par mois clôturé (month = 1er jour du mois).
--    fixed_incomes, charges et savings_target figent le budget prévu au moment du point,
--    pour que les anciens bilans ne changent pas quand une charge est modifiée.
CREATE TABLE IF NOT EXISTS checkpoints (
    month          date          PRIMARY KEY CHECK (extract(day FROM month) = 1),
    taken_on       date          NOT NULL,
    total_balance  numeric(12,2) NOT NULL,
    income         numeric(12,2) NOT NULL CHECK (income >= 0),
    fixed_incomes  numeric(12,2) NOT NULL,
    charges        numeric(12,2) NOT NULL,
    savings_target numeric(12,2) NOT NULL
);

-- 4. Enregistre un point en une seule transaction : nouveaux soldes + relevé du mois.
--    p_balances : [{"id": 1, "balance": "1350.50"}, ...]. Refaire le point d'un mois le remplace.
CREATE OR REPLACE FUNCTION record_checkpoint(
    p_month          date,
    p_taken_on       date,
    p_income         numeric,
    p_fixed_incomes  numeric,
    p_charges        numeric,
    p_savings_target numeric,
    p_balances       jsonb
) RETURNS checkpoints
LANGUAGE plpgsql
AS $$
DECLARE
    v_checkpoint checkpoints;
BEGIN
    UPDATE accounts AS a
    SET previous_balance   = a.balance,
        balance            = (b.value ->> 'balance')::numeric,
        balance_updated_on = p_taken_on
    FROM jsonb_array_elements(p_balances) AS b(value)
    WHERE a.id = (b.value ->> 'id')::bigint;

    INSERT INTO checkpoints (month, taken_on, total_balance, income, fixed_incomes, charges, savings_target)
    SELECT p_month, p_taken_on, COALESCE(sum(balance), 0), p_income, p_fixed_incomes, p_charges, p_savings_target
    FROM accounts
    ON CONFLICT (month) DO UPDATE
    SET taken_on       = EXCLUDED.taken_on,
        total_balance  = EXCLUDED.total_balance,
        income         = EXCLUDED.income,
        fixed_incomes  = EXCLUDED.fixed_incomes,
        charges        = EXCLUDED.charges,
        savings_target = EXCLUDED.savings_target
    RETURNING * INTO v_checkpoint;

    RETURN v_checkpoint;
END;
$$;

-- Le bot se connecte avec la clé anon : mêmes droits que sur les tables existantes.
GRANT SELECT, INSERT, UPDATE ON budget_settings TO anon;
GRANT SELECT, INSERT, UPDATE ON checkpoints TO anon;
GRANT EXECUTE ON FUNCTION record_checkpoint(date, date, numeric, numeric, numeric, numeric, jsonb) TO anon;
