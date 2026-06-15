from datetime import date, timedelta
from groq import Groq
from app.core.config import GROQ_API_KEY
from app.core.reporting import get_monthly_summary
from app.core.database import supabase


def _get_last_30_days_expenses() -> list:
    start = (date.today() - timedelta(days=30)).isoformat()
    return (
        supabase.table("expenses")
        .select("amount, category, date")
        .gte("date", start)
        .order("date")
        .execute()
        .data
    )


def generate_weekly_report() -> str:
    today = date.today()
    s = get_monthly_summary(today.year, today.month)
    expenses_detail = _get_last_30_days_expenses()

    by_cat = "\n".join(f"- {cat} : {total:.2f} €" for cat, total in s["by_category"].items()) or "- Aucune dépense"
    accounts = "\n".join(f"- {a['name']} : {a['balance']:.2f} €" for a in s["accounts"]) or "- Aucun compte"
    charges = "\n".join(f"- {c['name']} : {c['amount']:.2f} € / {c['frequency']}" for c in s["charges_list"]) or "- Aucune charge"
    detail = "\n".join(
        f"- {r['date']} | {r['category'] or 'Autre'} | {float(r['amount']):.2f} €"
        for r in expenses_detail
    ) or "- Aucune dépense"

    projection = f"{s['projection']:.2f} €" if s.get("projection") is not None else "N/A"

    context = f"""Données financières — {today.strftime('%d/%m/%Y')}

MOIS EN COURS ({s['days_elapsed']}/{s['days_in_month']} jours) :
- Revenus : {s['incomes']:.2f} €
- Dépenses : {s['expenses']:.2f} €
- Charges fixes : {s['charges']:.2f} €
- Cashflow : {s['cashflow']:.2f} €
- Projection fin de mois : {projection}

PAR CATÉGORIE :
{by_cat}

SEMAINE EN COURS : {s['week_expenses']:.2f} € vs {s['prev_week_expenses']:.2f} € (semaine précédente) {s['delta_week']}

COMPTES :
{accounts}

CHARGES FIXES :
{charges}

VS MOIS PRÉCÉDENT :
- Revenus : {s['prev_incomes']:.2f} € → {s['incomes']:.2f} € {s['delta_incomes']}
- Dépenses : {s['prev_expenses']:.2f} € → {s['expenses']:.2f} € {s['delta_expenses']}
- Cashflow : {s['prev_cashflow']:.2f} € → {s['cashflow']:.2f} € {s['delta_cashflow']}

DÉPENSES 30 DERNIERS JOURS :
{detail}
"""

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=800,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un conseiller financier personnel concis et direct. "
                    "Analyse les données et produis un rapport hebdomadaire en français. "
                    "Identifie les tendances, les points d'attention, et donne 2-3 recommandations concrètes. "
                    "Format : courts paragraphes, direct, pas de listes à rallonge."
                ),
            },
            {
                "role": "user",
                "content": f"Voici mes données financières. Fais mon rapport de la semaine :\n\n{context}",
            },
        ],
    )
    return response.choices[0].message.content.strip()
