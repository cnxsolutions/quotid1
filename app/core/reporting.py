from concurrent.futures import ThreadPoolExecutor
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


def _sum_amount(table: str, gte: str, lt: str) -> float:
    rows = supabase.table(table).select("amount").gte("date", gte).lt("date", lt).execute().data
    return sum(float(r["amount"]) for r in rows)


def _week_range(offset: int = 0) -> tuple[str, str]:
    today = date.today()
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
    sunday = monday + timedelta(days=7)
    return monday.isoformat(), sunday.isoformat()


def get_monthly_summary(year: int, month: int) -> dict:
    start, end = _month_range(year, month)
    py, pm = _prev_month(year, month)
    py_start, py_end = _month_range(py, pm)
    w0_start, w0_end = _week_range(0)
    w1_start, w1_end = _week_range(1)

    # Toutes ces requêtes sont indépendantes : on les lance en parallèle
    # plutôt qu'en série pour éviter d'empiler les latences réseau.
    with ThreadPoolExecutor(max_workers=8) as pool:
        f_exp_rows = pool.submit(
            lambda: supabase.table("expenses").select("amount, category").gte("date", start).lt("date", end).execute().data
        )
        f_inc_rows = pool.submit(
            lambda: supabase.table("incomes").select("amount").gte("date", start).lt("date", end).execute().data
        )
        f_charge_rows = pool.submit(lambda: supabase.table("charges").select("name, amount, frequency").execute().data)
        f_accounts = pool.submit(get_accounts)
        f_prev_inc = pool.submit(_sum_amount, "incomes", py_start, py_end)
        f_prev_exp = pool.submit(_sum_amount, "expenses", py_start, py_end)
        f_week_exp = pool.submit(_sum_amount, "expenses", w0_start, w0_end)
        f_prev_week_exp = pool.submit(_sum_amount, "expenses", w1_start, w1_end)

        exp_rows = f_exp_rows.result()
        inc_rows = f_inc_rows.result()
        charge_rows = f_charge_rows.result()
        account_rows = f_accounts.result()
        prev_inc = f_prev_inc.result()
        prev_exp = f_prev_exp.result()
        week_exp = f_week_exp.result()
        prev_week_exp = f_prev_week_exp.result()

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

    prev_cashflow = prev_inc - prev_exp

    def _delta(current: float, previous: float) -> str:
        if previous == 0:
            return ""
        pct = ((current - previous) / previous) * 100
        arrow = "▲" if pct > 0 else "▼"
        return f" {arrow}{abs(pct):.0f}%"

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
