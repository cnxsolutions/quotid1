from datetime import date, timedelta
from app.core.database import supabase
from app.core.accounts import get_accounts


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1).isoformat()
    if month == 12:
        end = date(year + 1, 1, 1).isoformat()
    else:
        end = date(year, month + 1, 1).isoformat()
    return start, end


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year, month - 1) if month > 1 else (year - 1, 12)


def _fetch_month(year: int, month: int) -> tuple[float, float]:
    start, end = _month_range(year, month)
    exp = sum(
        float(r["amount"])
        for r in supabase.table("expenses").select("amount").gte("date", start).lt("date", end).execute().data
    )
    inc = sum(
        float(r["amount"])
        for r in supabase.table("incomes").select("amount").gte("date", start).lt("date", end).execute().data
    )
    return inc, exp


def _week_range(offset: int = 0) -> tuple[str, str]:
    today = date.today()
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
    sunday = monday + timedelta(days=7)
    return monday.isoformat(), sunday.isoformat()


def get_monthly_summary(year: int, month: int) -> dict:
    start, end = _month_range(year, month)

    exp_rows = (
        supabase.table("expenses").select("amount, category")
        .gte("date", start).lt("date", end).execute().data
    )
    inc_rows = (
        supabase.table("incomes").select("amount")
        .gte("date", start).lt("date", end).execute().data
    )
    charge_rows = supabase.table("charges").select("name, amount, frequency").execute().data
    account_rows = get_accounts()

    total_expenses = sum(float(r["amount"]) for r in exp_rows)
    total_incomes = sum(float(r["amount"]) for r in inc_rows)
    total_charges = sum(
        float(r["amount"]) if r["frequency"] == "Mensuel" else float(r["amount"]) / 12
        for r in charge_rows
    )
    cashflow = total_incomes - total_expenses

    by_category: dict[str, float] = {}
    for r in exp_rows:
        cat = r["category"] or "Autre"
        by_category[cat] = by_category.get(cat, 0.0) + float(r["amount"])

    # Mois précédent
    py, pm = _prev_month(year, month)
    prev_inc, prev_exp = _fetch_month(py, pm)
    prev_cashflow = prev_inc - prev_exp

    def _delta(current: float, previous: float) -> str:
        if previous == 0:
            return ""
        pct = ((current - previous) / previous) * 100
        arrow = "▲" if pct > 0 else "▼"
        return f" {arrow}{abs(pct):.0f}%"

    # Semaine courante vs semaine précédente
    w0_start, w0_end = _week_range(0)
    w1_start, w1_end = _week_range(1)

    week_exp = sum(
        float(r["amount"])
        for r in supabase.table("expenses").select("amount").gte("date", w0_start).lt("date", w0_end).execute().data
    )
    prev_week_exp = sum(
        float(r["amount"])
        for r in supabase.table("expenses").select("amount").gte("date", w1_start).lt("date", w1_end).execute().data
    )

    # Rythme : projection fin de mois
    today = date.today()
    days_elapsed = (today - date(year, month, 1)).days + 1
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    variable_expenses = total_expenses - total_charges
    projection = (variable_expenses / days_elapsed * days_in_month + total_charges) if days_elapsed > 0 and year == today.year and month == today.month else None

    return {
        "year": year,
        "month": month,
        "incomes": total_incomes,
        "expenses": total_expenses,
        "charges": total_charges,
        "charges_list": [{"name": r["name"], "amount": float(r["amount"]), "frequency": r["frequency"]} for r in charge_rows],
        "cashflow": cashflow,
        "by_category": dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)),
        "accounts": [{"name": a["name"], "balance": float(a["balance"])} for a in account_rows],
        "prev_incomes": prev_inc,
        "prev_expenses": prev_exp,
        "prev_cashflow": prev_cashflow,
        "delta_incomes": _delta(total_incomes, prev_inc),
        "delta_expenses": _delta(total_expenses, prev_exp),
        "delta_cashflow": _delta(cashflow, prev_cashflow),
        "week_expenses": week_exp,
        "prev_week_expenses": prev_week_exp,
        "delta_week": _delta(week_exp, prev_week_exp),
        "projection": projection,
        "days_in_month": days_in_month,
        "days_elapsed": days_elapsed if year == today.year and month == today.month else days_in_month,
    }
