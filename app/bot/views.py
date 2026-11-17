"""Messages Telegram (HTML). Les tableaux passent en <pre> : police à chasse fixe, montants alignés.

Largeur d'une ligne : 28 caractères, lisible sans retour à la ligne sur un écran de 375 px.
"""

from datetime import date
from decimal import Decimal
from html import escape

from app.bot.money import format_eur
from app.bot.months import month_abbr, month_name, of_month
from app.core.models import (
    MONTHS_PER_YEAR,
    Account,
    AccountKind,
    Change,
    Frequency,
    MonthProgress,
    MonthReview,
    Overview,
    ProgressStatus,
    RecurringItem,
    add_months,
    monthly_total,
    total_balance,
)
from app.core.monthly_point import PointDraft, PointOutcome
from app.core.savings import GoalStatus, SavingsPlan

_LABEL_WIDTH = 14
_AMOUNT_WIDTH = 13
_KIND_HEADERS = {AccountKind.CURRENT: "COURANT", AccountKind.SAVINGS: "ÉPARGNE"}
_PROJECTION_MONTHS = (6, 12)
_COVERAGE_ADVICE_MIN = Decimal("3")


# ── Briques ──────────────────────────────────────────────────────────────────


def _fit(label: str) -> str:
    return label if len(label) <= _LABEL_WIDTH else label[: _LABEL_WIDTH - 1] + "…"


def _line(label: str, amount: Decimal, *, signed: bool = False) -> str:
    return f"{_fit(label):<{_LABEL_WIDTH}} {format_eur(amount, signed=signed):>{_AMOUNT_WIDTH}}"


def _pre(lines: list[str]) -> str:
    return "<pre>" + escape("\n".join(lines)) + "</pre>"


def short_date(day: date, today: date) -> str:
    return day.strftime("%d/%m" if day.year == today.year else "%d/%m/%Y")


def _upcoming_text(title: str, upcoming: list[tuple[date, RecurringItem]]) -> str:
    lines = [f"• {month_name(month)} : {escape(item.name)} — {format_eur(item.amount)}" for month, item in upcoming]
    return f"📅 <b>{title}</b>\n" + "\n".join(lines)


def _account_lines(accounts: list[Account] | tuple[Account, ...], today: date, *, details: bool) -> list[str]:
    """Comptes regroupés par type (avec sous-total) dès qu'il y a du courant et de l'épargne."""
    grouped = len({account.kind for account in accounts}) > 1
    indent = "  " if grouped else ""
    lines: list[str] = []
    for kind in AccountKind:
        group = [account for account in accounts if account.kind is kind]
        if not group:
            continue
        if grouped:
            lines.append(_line(_KIND_HEADERS[kind], total_balance(group)))
        for account in group:
            lines.append(_line(indent + account.name, account.balance))
            detail = _account_detail(account, today) if details else None
            if detail is not None:
                lines.append(f"{indent}  ↳ {detail}")
    return lines


def _account_detail(account: Account, today: date) -> str | None:
    parts: list[str] = []
    if account.updated_on is not None:
        parts.append(f"màj {short_date(account.updated_on, today)}")
    if account.last_change is not None:
        parts.append(format_eur(account.last_change, signed=True))
    return " · ".join(parts) if parts else None


# ── Sections ─────────────────────────────────────────────────────────────────


def render_accounts(title: str, accounts: list[Account], empty_text: str, today: date) -> str:
    if not accounts:
        return f"<b>{title}</b>\n\n{empty_text}"
    lines = _account_lines(accounts, today, details=True)
    if len(accounts) > 1:
        lines += ["", _line("Total", total_balance(accounts))]
    return f"<b>{title}</b>\n{_pre(lines)}"


def render_recurring(title: str, items: list[RecurringItem], empty_text: str) -> str:
    if not items:
        return f"<b>{title}</b>\n\n{empty_text}"
    lines: list[str] = []
    undated = False
    for item in items:
        lines.append(_line(item.name, item.amount))
        if item.frequency is Frequency.YEARLY:
            when = month_abbr(item.due_month) if item.due_month is not None else "annuel"
            undated = undated or item.due_month is None
            lines.append(f"  ↳ {when} · {format_eur(item.monthly_amount)}/mois")
    monthly = monthly_total(items)
    lines += ["", _line("Total / mois", monthly), _line("Total / an", monthly * MONTHS_PER_YEAR)]
    text = f"<b>{title}</b>\n{_pre(lines)}"
    if undated:
        text += "\n<i>📅 Indique le mois d'échéance de tes charges annuelles : rappel à l'avance et bilan exact.</i>"
    return text


def render_change(change: Change, today: date) -> str:
    lines = [
        _line("Avant", change.before),
        _line("Maintenant", change.after),
        _line("Écart", change.delta, signed=True),
    ]
    text = f"✅ Mise à jour : <b>{escape(change.name)}</b>\n{_pre(lines)}"
    if change.previous_date is not None:
        text += f"\n<i>Écart depuis le {short_date(change.previous_date, today)}.</i>"
    return text


# ── Vue globale ──────────────────────────────────────────────────────────────


def _progress_text(progress: MonthProgress, today: date) -> str:
    since = progress.since
    if progress.status is ProgressStatus.NO_POINT or since is None:
        return "<i>📍 Fais ton premier point du mois pour suivre tes dépenses et ton épargne.</i>"
    if progress.status is ProgressStatus.POINT_DUE and progress.due_month is not None:
        return f"📍 <b>Le point {of_month(progress.due_month)} est à faire</b> : ta paie est tombée."
    header = f"<b>Ce mois-ci</b> · depuis le point du {short_date(since.taken_on, today)}"
    if progress.status is ProgressStatus.STALE:
        return f"{header}\n<i>Mets à jour ton compte courant (🏦 Comptes → 🔄) pour voir où tu en es.</i>"
    lines = [_line("Dépensé", progress.spent), _line("Reste", progress.remaining)]
    text = f"{header}\n{_pre(lines)}\n<i>Reste = revenus fixes − épargne visée − dépensé (charges comprises).</i>"
    if progress.remaining < 0:
        text += f"\n⚠️ Tu entames ton épargne visée de {format_eur(-progress.remaining)}."
    return text


def render_overview(overview: Overview, today: date) -> str:
    title = "<b>📊 Vue globale</b>"
    if overview.is_empty:
        return (
            f"{title}\n\nRien à afficher pour l'instant.\nAjoute tes comptes, charges et revenus fixes depuis le menu."
        )
    accounts = _account_lines(overview.accounts, today, details=False) or ["Comptes : aucun"]
    lines = [
        *accounts,
        _line("TOTAL", overview.total_balance),
        "",
        "PAR MOIS",
        _line("Revenus fixes", overview.monthly_incomes),
        _line("Charges", -overview.monthly_charges),
        _line("Épargne visée", -overview.savings_target),
        _line("Vie courante", overview.living_budget),
    ]
    text = f"{title}\n{_pre(lines)}"
    if overview.living_budget < 0:
        text += "\n⚠️ Tes charges et ton épargne visée dépassent tes revenus fixes."
    upcoming = overview.upcoming(today)
    if upcoming:
        text += "\n\n" + _upcoming_text("Prochaines échéances", upcoming)
    return f"{text}\n\n{_progress_text(overview.progress(today), today)}"


# ── Épargne ──────────────────────────────────────────────────────────────────


def render_target_prompt(current: Decimal, living_budget: Decimal) -> str:
    return (
        f"💶 <b>Épargne visée</b> : {format_eur(current)} / mois\n"
        f"Budget de vie courante qui en découle : {format_eur(living_budget)} / mois\n\n"
        "Combien veux-tu mettre de côté chaque mois ? (0 pour rien)"
    )


def _goal_text(position: int, status: GoalStatus) -> str:
    goal = status.goal
    head = f"{position}. <b>{escape(goal.name)}</b> · {format_eur(status.funded)} / {format_eur(goal.amount)}"
    if goal.deadline is not None:
        head += f" · {month_name(goal.deadline)}"
    if status.reached:
        return f"{head}\n   ✅ Atteint"
    if status.overdue:
        return f"{head}\n   ⚠️ Date dépassée : il manque {format_eur(status.gap)}"
    details: list[str] = []
    if status.required_per_month is not None:
        details.append(f"il faut {format_eur(status.required_per_month)}/mois")
    else:
        details.append(f"il manque {format_eur(status.gap)}")
    if status.eta is not None:
        verdict = {True: " ✅", False: " ⚠️ en retard", None: ""}[status.on_track]
        details.append(f"au rythme actuel : {month_name(status.eta)}{verdict}")
    sentence = " · ".join(details)
    return f"{head}\n   {sentence[0].upper()}{sentence[1:]}"


def render_savings(plan: SavingsPlan) -> str:
    lines = [_line("Épargne", plan.savings_balance)]
    if plan.monthly_pace is not None:
        lines.append(_line("Rythme / mois", plan.monthly_pace, signed=True))
        for months in _PROJECTION_MONTHS:
            projected = plan.projection(months)
            if projected is not None:
                lines.append(_line(f"Dans {months} mois", projected))
    lines += ["", _line("Visée / mois", plan.savings_target), _line("Vie courante", plan.living_budget)]
    parts = [f"<b>🎯 Épargne</b>\n{_pre(lines)}"]

    notes: list[str] = []
    if not plan.has_savings_accounts:
        notes.append("⚠️ Aucun compte classé en épargne : 🏦 Comptes → 🏷 Type.")
    if plan.monthly_pace is None:
        notes.append("<i>Rythme et projections : disponibles après deux points du mois.</i>")
    else:
        notes.append(f"<i>Rythme mesuré sur {plan.pace_months} mois. Vie courante = budget mensuel restant.</i>")
    coverage = plan.coverage_months
    if coverage is not None and plan.has_savings_accounts:
        advice = " ⚠️ On conseille 3 à 6 mois." if coverage < _COVERAGE_ADVICE_MIN else ""
        coverage_text = f"{coverage:.1f}".replace(".", ",")
        notes.append(
            f"🛟 Ton épargne couvre <b>{coverage_text} mois</b> de dépenses "
            f"({format_eur(plan.monthly_expenses)}/mois).{advice}"
        )
    parts.append("\n".join(notes))

    if plan.goals:
        goals = "\n".join(_goal_text(i, status) for i, status in enumerate(plan.goals, start=1))
        parts.append(
            f"<b>Objectifs</b>\n{goals}\n"
            "<i>Ton épargne remplit d'abord les objectifs sans date, puis les autres par date.</i>"
        )
    else:
        parts.append(
            "<b>Objectifs</b>\nAucun pour l'instant : « ➕ Ajouter » pour viser un projet "
            "(voyage, voiture…) ou un matelas de sécurité."
        )
    return "\n\n".join(parts)


# ── Point du mois ────────────────────────────────────────────────────────────


def render_point_reminder(month: date, upcoming: list[tuple[date, RecurringItem]]) -> str:
    text = (
        f"📍 <b>C'est l'heure du point {of_month(month)}</b>\n"
        "Ta paie est tombée : relève tes comptes en 2 minutes pour voir ce que tu as dépensé et épargné.\n"
        "Appuie sur « 📍 Point du mois »."
    )
    if upcoming:
        text += "\n\n" + _upcoming_text("À prévoir", upcoming)
    return text


def render_point_intro(draft: PointDraft) -> str:
    count = len(draft.accounts)
    text = (
        f"📍 <b>Point {of_month(draft.month)}</b>\n"
        f"{count} compte{'s' if count > 1 else ''} à relever, rien n'est enregistré avant la fin."
    )
    if draft.replacing:
        text += "\n<i>Ce point existe déjà : il sera remplacé.</i>"
    if draft.previous is None:
        text += "\n<i>Premier point : il servira de référence pour les prochains bilans.</i>"
    return text


def render_point_account(account: Account, position: int, count: int, today: date) -> str:
    text = f"🏦 <b>{escape(account.name)}</b> ({position}/{count})\nDernier solde : {format_eur(account.balance)}"
    if account.updated_on is not None:
        text += f" (màj {short_date(account.updated_on, today)})"
    return f"{text}\nNouveau solde ?"


def render_point_ack(account: Account, balance: Decimal) -> str:
    delta = balance - account.balance
    change = "inchangé" if delta == 0 else format_eur(delta, signed=True)
    return f"✓ {escape(account.name)} : {format_eur(balance)} ({change})"


def render_point_income(draft: PointDraft, today: date) -> str:
    since = f" depuis le point du {short_date(draft.previous.taken_on, today)}" if draft.previous else ""
    text = f"💼 <b>Revenus reçus</b>{since}"
    if draft.monthly_fixed_incomes <= 0:
        return f"{text}\nAucun revenu fixe enregistré : tape le montant reçu (0 si rien)."
    months = f" sur {draft.months} mois" if draft.months > 1 else ""
    return (
        f"{text}\nRevenus fixes prévus{months} : {format_eur(draft.expected_income)}\n"
        "Si c'est bien ça, touche le bouton. Sinon tape le montant réel (prime, remboursement, vente…)."
    )


def _living_verdict(review: MonthReview, has_undated_yearly: bool) -> str:
    budget = review.living_budget
    gap = review.living - budget
    if gap <= 0:
        return f"✅ Vie courante : {format_eur(-gap)} sous le budget ({format_eur(budget)})"
    text = f"⚠️ Vie courante : {format_eur(gap)} au-dessus du budget ({format_eur(budget)})"
    if has_undated_yearly:
        text += "\n<i>Une charge annuelle sans mois d'échéance (📦 Charges → 📅) peut fausser ce chiffre.</i>"
    return text


def _savings_verdict(review: MonthReview) -> str | None:
    goal = review.savings_goal
    saved = review.net_saved
    label = "Épargne nette" if review.provisions != 0 else "Épargne"
    if goal <= 0:
        return f"⚠️ Tes comptes ont baissé de {format_eur(-review.saved)}." if review.saved < 0 else None
    if saved >= goal:
        return f"✅ {label} : objectif de {format_eur(goal)} atteint ({format_eur(saved - goal, signed=True)})"
    return f"⚠️ {label} : {format_eur(saved)} pour {format_eur(goal)} visés ({format_eur(saved - goal, signed=True)})"


def render_point_outcome(outcome: PointOutcome, today: date) -> str:
    checkpoint = outcome.checkpoint
    replaced = "\n<i>Remplace le point déjà enregistré pour ce mois.</i>" if outcome.replaced else ""
    upcoming = "\n\n" + _upcoming_text("À prévoir", outcome.upcoming) if outcome.upcoming else ""
    review = outcome.review
    if review is None:
        return (
            f"📍 <b>Premier point enregistré</b> ({month_name(checkpoint.month)})\n"
            f"Total de tes comptes : <b>{format_eur(checkpoint.total_balance)}</b>\n\n"
            "Il sert de référence : ton premier bilan (dépenses, épargne) arrivera "
            f"au prochain point, fin {month_name(add_months(checkpoint.month, 1))}.{replaced}{upcoming}"
        )
    lines = [
        _line("Total comptes", checkpoint.total_balance),
        _line("Revenus reçus", checkpoint.income),
        _line("Épargné", review.saved, signed=True),
    ]
    if review.provisions != 0:
        lines += [
            _line("  provisions", review.provisions, signed=True),
            _line("  nette", review.net_saved, signed=True),
        ]
    lines += [
        _line("Dépensé", review.spent),
        _line("  charges", review.charges),
        _line("  vie courante", review.living),
    ]
    verdicts = [_living_verdict(review, outcome.has_undated_yearly)]
    savings = _savings_verdict(review)
    if savings is not None:
        verdicts.append(savings)
    if review.provisions != 0:
        verdicts.append(
            "<i>Provisions : part de tes charges annuelles mise de côté (négative le mois d'une échéance).</i>"
        )
    period = f"depuis le point du {short_date(review.previous.taken_on, today)}"
    if review.months > 1:
        period += f", sur {review.months} mois"
    return (
        f"📍 <b>Bilan {of_month(checkpoint.month)}</b>\n{_pre(lines)}\n"
        + "\n".join(verdicts)
        + f"\n<i>Calculé {period}.</i>{replaced}{upcoming}"
    )
