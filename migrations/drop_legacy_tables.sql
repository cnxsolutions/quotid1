-- OPTIONNEL et IRRÉVERSIBLE : efface les données des fonctionnalités retirées du bot
-- (dépenses, revenus ponctuels, tâches, projets).
-- Le bot n'en a plus besoin. Seule conséquence si tu les gardes : un compte encore référencé
-- par une ancienne dépense ou un ancien revenu ne peut pas être supprimé.
-- Exporte ces tables avant (Table Editor > Export to CSV) si tu veux garder une trace.

DROP TABLE IF EXISTS expenses, incomes, tasks, projects;
