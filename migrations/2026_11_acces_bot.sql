-- Accès du bot aux tables créées par les migrations 2026_11_*.
-- Supabase active automatiquement la sécurité par ligne (RLS) sur les nouvelles tables : sans
-- politique, la clé anon du bot ne peut ni les lire ni y écrire (erreur 42501). On lui donne le
-- même accès complet qu'aux tables historiques (accounts, charges).
-- À exécuter dans Supabase > SQL Editor APRÈS 2026_11_echeances_objectifs.sql.
-- Idempotent : peut être rejoué sans risque.

DO $$
DECLARE
    v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['fixed_incomes', 'budget_settings', 'checkpoints', 'savings_goals'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('DROP POLICY IF EXISTS bot_full_access ON %I', v_table);
        EXECUTE format(
            'CREATE POLICY bot_full_access ON %I FOR ALL TO anon USING (true) WITH CHECK (true)', v_table
        );
    END LOOP;
END;
$$;

-- La ligne unique des réglages (créée par 2026_11_point_mensuel.sql, rejouée par sécurité).
INSERT INTO budget_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
