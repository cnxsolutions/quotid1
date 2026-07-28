import html
from datetime import date as Date


def esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    s = f"{abs(value):,.2f}"
    intpart, dec = s.split(".")
    intpart = intpart.replace(",", " ")
    return f"{sign}{intpart},{dec} €"


def money_signed(value: float) -> str:
    return f"+{money(value)}" if value > 0 else money(value)


def bar(pct: float, width: int = 10) -> str:
    pct = max(0.0, min(1.0, pct))
    filled = round(pct * width)
    return "█" * filled + "░" * (width - filled)


def pre(lines: list[str]) -> str:
    return "<pre>" + "\n".join(lines) + "</pre>"


def hr(width: int) -> str:
    return "─" * width


def category_bars(by_category: dict, width: int = 10) -> str:
    if not by_category:
        return ""
    max_val = max(by_category.values()) or 1.0
    name_w = min(max((len(c) for c in by_category), default=4), 10)
    lines = []
    for cat, total in by_category.items():
        label = esc(cat)[:name_w].ljust(name_w)
        lines.append(f"{label} {bar(total / max_val, width)} {money(total):>12}")
    return "\n".join(lines)


def accounts_block(accounts: list) -> str:
    if not accounts:
        return "Aucun compte."
    name_w = max((len(a["name"]) for a in accounts), default=5)
    lines = [f"{esc(a['name']):<{name_w}} {money(a['balance']):>13}" for a in accounts]
    if len(accounts) > 1:
        total = sum(a["balance"] for a in accounts)
        lines.append(hr(name_w + 14))
        lines.append(f"{'Total':<{name_w}} {money(total):>13}")
    return pre(lines)


def charges_block(charges: list) -> str:
    if not charges:
        return "Aucune charge."
    name_w = min(max((len(c["name"]) for c in charges), default=5), 20)
    lines = []
    for c in charges:
        label = truncate(esc(c["name"]), name_w).ljust(name_w)
        lines.append(f"{label} {money(c['amount']):>13} / {c['frequency']}")
    return pre(lines)


def movement_confirmation(
    kind: str,
    amount: float,
    description: str = "",
    category: str | None = None,
    account: str | None = None,
    project: str | None = None,
    d: Date | None = None,
) -> str:
    label = "Dépense" if kind == "expense" else "Revenu"
    parts = [f"<b>{money(amount)}</b>"]
    if description:
        parts.append(esc(description))
    if category:
        parts.append(esc(category))
    if account:
        parts.append(esc(account))
    if project:
        parts.append(esc(project))
    if d:
        parts.append(d.strftime("%d/%m/%Y"))
    return f"✅ {label} · " + " · ".join(parts)


def confirmation(label: str, name: str, extra: list[str] | None = None) -> str:
    msg = f"✅ {label} · <b>{esc(name)}</b>"
    if extra:
        msg += " · " + " · ".join(extra)
    return msg


def task_confirmation(description: str, project: str | None = None, due_date: Date | None = None) -> str:
    extra = [esc(project)] if project else []
    if due_date:
        extra.append(f"📅 {due_date.strftime('%d/%m/%Y')}")
    return confirmation("Tâche ajoutée", description, extra)


def step_prompt(question: str, recap: list[str] | None = None) -> str:
    if recap:
        return " · ".join(recap) + "\n" + f"<b>{question}</b>"
    return f"<b>{question}</b>"


def error(text: str) -> str:
    return f"❌ {text}"


def task_urgency_badge(due_date: str | None) -> str:
    if not due_date:
        return "⚪"
    from datetime import date as _date
    delta = (_date.fromisoformat(due_date) - _date.today()).days
    if delta < 0:
        return "🔴"
    if delta == 0:
        return "🟠"
    if delta == 1:
        return "🟡"
    if delta <= 3:
        return "🟢"
    return "⚪"


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def projects_block(projects: list) -> str:
    if not projects:
        return "Aucun projet."
    ordered = sorted(projects, key=lambda p: p["total"], reverse=True)
    name_w = min(max((len(p["name"]) for p in ordered), default=5), 20)
    lines = []
    for p in ordered:
        label = truncate(esc(p["name"]), name_w).ljust(name_w)
        n = p["count"]
        lines.append(f"{label} {money(p['total']):>13}  {n} revenu{'s' if n != 1 else ''}")
    if len(ordered) > 1:
        total = sum(p["total"] for p in ordered)
        lines.append(hr(name_w + 14))
        lines.append(f"{'Total':<{name_w}} {money(total):>13}  {len(ordered)} projets")
    return pre(lines)


def history_block(rows: list, empty_text: str) -> str:
    if not rows:
        return empty_text
    lines = [
        f"{(r.get('date') or '—'):<10} {money(float(r['amount'])):>12}  {esc(r.get('category') or 'Sans catégorie')}"
        for r in rows
    ]
    return pre(lines)


def markdown_bold_to_html(text: str) -> str:
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))
