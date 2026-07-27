import asyncio
from datetime import date as Date
from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from app.core.config import TELEGRAM_ALLOWED_USER_ID
from app.core.expenses import insert_expense, get_recent_expenses
from app.core.incomes import insert_income, get_recent_incomes
from app.core.tasks import insert_task, get_pending_tasks, mark_done, get_tasks_due_tomorrow
from app.core.accounts import get_accounts, get_default_account, insert_account
from app.core.utils import CATEGORIES, parse_date
from app.core.reporting import get_monthly_summary
from app.core.charges import insert_charge, get_charges
from app.core.projects import insert_project, get_projects, get_projects_with_summary

# ── Boutons ──────────────────────────────────────────────────────────────────

BTN_FINANCE = "💰 Finances"
BTN_TASKS = "✅ Tâches"
BTN_GESTION = "⚙️ Gestion"
BTN_SUMMARY = "📊 Résumé du mois"

BTN_EXPENSE = "💸 Dépense"
BTN_INCOME = "💰 Revenu"
BTN_CASH = "💳 Soldes"
BTN_CHARGES = "📦 Charges fixes"
BTN_HISTORY = "🕘 Historique"

BTN_NEW_TASK = "➕ Nouvelle tâche"
BTN_TODAY = "📋 Mes tâches"
BTN_TASK_DONE = "☑️ Terminer tâche"

BTN_ACCOUNTS = "🏦 Comptes"
BTN_PROJECTS = "🗂 Projets"
BTN_NEW_CHARGE = "➕ Nouvelle charge"

BTN_NEW_ACCOUNT = "➕ Nouveau compte"
BTN_ACCOUNTS_BALANCE = "📊 Soldes"
BTN_NEW_PROJECT = "➕ Nouveau projet"
BTN_PROJECTS_LIST = "📋 Liste"

BTN_SKIP = "Passer"
BTN_BACK = "⬅️ Retour"
BTN_TODAY_DATE = "Aujourd'hui"
BTN_YESTERDAY = "Hier"
BTN_CUSTOM_DATE = "📅 Saisir date"

# ── États ────────────────────────────────────────────────────────────────────

(
    WAITING_MAIN_MENU,
    WAITING_FINANCE_MENU,
    WAITING_TASKS_MENU,
    WAITING_GESTION_MENU,
    WAITING_ACCOUNTS_MENU,
    WAITING_PROJECTS_MENU,
    WAITING_EXPENSE_AMOUNT,
    WAITING_EXPENSE_CATEGORY,
    WAITING_EXPENSE_ACCOUNT,
    WAITING_EXPENSE_DATE,
    WAITING_EXPENSE_DATE_INPUT,
    WAITING_INCOME_AMOUNT,
    WAITING_INCOME_CATEGORY,
    WAITING_INCOME_ACCOUNT,
    WAITING_INCOME_PROJECT,
    WAITING_INCOME_DATE,
    WAITING_INCOME_DATE_INPUT,
    WAITING_TASK,
    WAITING_TASK_PROJECT,
    WAITING_TASK_DUE,
    WAITING_TASK_DUE_INPUT,
    WAITING_DONE_SELECT,
    WAITING_CHARGE_NAME,
    WAITING_CHARGE_AMOUNT,
    WAITING_CHARGE_FREQ,
    WAITING_CHARGE_ACCOUNT,
    WAITING_ACCOUNT_NAME,
    WAITING_ACCOUNT_BALANCE,
    WAITING_PROJECT_NAME,
) = range(29)

# ── Claviers ─────────────────────────────────────────────────────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_FINANCE, BTN_TASKS],
        [BTN_GESTION, BTN_SUMMARY],
    ],
    resize_keyboard=True,
)

FINANCE_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_EXPENSE, BTN_INCOME],
        [BTN_CASH, BTN_CHARGES],
        [BTN_HISTORY],
        [BTN_BACK],
    ],
    resize_keyboard=True,
)

TASKS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_NEW_TASK],
        [BTN_TODAY, BTN_TASK_DONE],
        [BTN_BACK],
    ],
    resize_keyboard=True,
)

GESTION_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_ACCOUNTS, BTN_PROJECTS],
        [BTN_NEW_CHARGE],
        [BTN_BACK],
    ],
    resize_keyboard=True,
)

ACCOUNTS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_NEW_ACCOUNT, BTN_ACCOUNTS_BALANCE],
        [BTN_BACK],
    ],
    resize_keyboard=True,
)

PROJECTS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_NEW_PROJECT, BTN_PROJECTS_LIST],
        [BTN_BACK],
    ],
    resize_keyboard=True,
)

FREQ_KEYBOARD = ReplyKeyboardMarkup(
    [["Mensuel", "Annuel"]],
    resize_keyboard=True,
)

DATE_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_TODAY_DATE, BTN_YESTERDAY], [BTN_CUSTOM_DATE, BTN_SKIP]],
    resize_keyboard=True,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _allowed(update: Update) -> bool:
    return update.effective_user.id == TELEGRAM_ALLOWED_USER_ID


def _escape_code(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _code_block(text: str) -> str:
    return f"```\n{_escape_code(text)}\n```"


def _project_keyboard() -> ReplyKeyboardMarkup:
    projects = get_projects()
    rows = [[p["name"]] for p in projects]
    rows.append([BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _account_keyboard() -> ReplyKeyboardMarkup:
    accounts = get_accounts()
    rows = [[a["name"]] for a in accounts]
    default = accounts[0]["name"] if accounts else None
    label = f"Passer (→ {default})" if default else "Passer"
    rows.append([label])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _resolve_account(raw: str) -> str | None:
    if raw.startswith("Passer"):
        return get_default_account()
    return raw.lower()


def _category_keyboard() -> ReplyKeyboardMarkup:
    rows = [[CATEGORIES[i], CATEGORIES[i + 1]] for i in range(0, len(CATEGORIES) - 1, 2)]
    if len(CATEGORIES) % 2:
        rows.append([CATEGORIES[-1]])
    rows.append([BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _format_confirmation(kind: str, amount: float, category: str | None, account_raw: str | None, d: Date | None) -> str:
    parts = [f"{amount:.2f} €"]
    if category:
        parts.append(category)
    if account_raw and account_raw != BTN_SKIP:
        parts.append(account_raw)
    if d:
        parts.append(d.strftime("%d/%m/%Y"))
    label = "Dépense" if kind == "expense" else "Revenu"
    return f"✅ {label} enregistré{'e' if kind == 'expense' else ''} : " + " · ".join(parts)


def _format_tasks(tasks: list) -> str:
    from datetime import date as _date
    today = _date.today()
    lines = []
    for t in tasks:
        if t.get("due_date"):
            due = _date.fromisoformat(t["due_date"])
            delta = (due - today).days
            if delta < 0:
                badge = "🔥"
            elif delta == 0:
                badge = "🔴"
            elif delta == 1:
                badge = "🟡"
            elif delta <= 3:
                badge = "🟠"
            else:
                badge = "○"
        else:
            badge = "○"

        line = f"{badge} {t['id']}. {t['description']}"
        if t.get("project_name"):
            line += f" [{t['project_name']}]"
        if t.get("due_date"):
            due = _date.fromisoformat(t["due_date"])
            delta = (due - today).days
            if delta < 0:
                line += f"  ← en retard {abs(delta)}j"
            elif delta == 0:
                line += f"  ← aujourd'hui"
            elif delta == 1:
                line += f"  ← demain"
            else:
                line += f"  ← {due.strftime('%d/%m')}"
        lines.append(line)
    return "\n".join(lines)


def _format_tasks_report(tasks: list, title: str) -> str:
    header = f"☀️ {title}\n\n"
    body = _format_tasks(tasks)
    count = len(tasks)
    summary = f"\n\n📌 {count} tâche{'s' if count > 1 else ''} au total"
    return header + body + summary


def _format_charges_display() -> str:
    charges = get_charges()
    if not charges:
        return "Aucune charge enregistrée."
    total_mensuel = 0.0
    lines = ["📦 CHARGES FIXES", ""]
    for c in charges:
        amount = float(c["amount"])
        freq = c["frequency"]
        mensuel = amount if freq == "Mensuel" else amount / 12
        total_mensuel += mensuel
        lines.append(f"{c['name']}")
        lines.append(f"  → {amount:.2f} € / {freq}")
        if c.get("account_name"):
            lines.append(f"  📌 {c['account_name']}")
        lines.append("")
    lines.append(f"💰 Total mensuel : {total_mensuel:.2f} €")
    lines.append(f"📅 Total annuel  : {total_mensuel * 12:.2f} €")
    lines.append("")
    lines.append("Quand débité → enregistrer en dépense catégorie « Charges »")
    return "\n".join(lines)


def _format_finance_history(n: int = 5) -> str:
    expenses = get_recent_expenses(n)
    incomes = get_recent_incomes(n)

    lines = ["🕘 HISTORIQUE FINANCIER", ""]

    if incomes:
        lines.append("Revenus récents")
        for row in incomes:
            date_text = row.get("date") or "-"
            category = row.get("category") or "Sans catégorie"
            lines.append(f"- {date_text} | {float(row['amount']):.2f} € | {category}")
    else:
        lines.append("Revenus récents")
        lines.append("- Aucun revenu récent")

    lines.append("")
    lines.append("Dépenses récentes")
    if expenses:
        for row in expenses:
            date_text = row.get("date") or "-"
            category = row.get("category") or "Sans catégorie"
            lines.append(f"- {date_text} | {float(row['amount']):.2f} € | {category}")
    else:
        lines.append("- Aucune dépense récente")

    return "\n".join(lines)


def _build_summary_lines(s: dict, month: int, year: int) -> list[str]:
    import calendar
    month_name = calendar.month_name[month].capitalize()
    sign = "+" if s["cashflow"] >= 0 else ""
    lines = [
        f"📊 RÉSUMÉ {month_name.upper()} {year}",
        "",
        f"Revenus :    {s['incomes']:>9.2f} € {s['delta_incomes']}",
        f"Dépenses :  {s['expenses']:>9.2f} € {s['delta_expenses']}",
        f"Charges :   {s['charges']:>9.2f} € (indicatif)",
        "",
        f"{'✓' if s['cashflow'] >= 0 else '⚠'} Cashflow : {sign}{s['cashflow']:>8.2f} € {s['delta_cashflow']}",
    ]

    if s.get("projection") is not None:
        lines.append(f"Projection : {s['projection']:.2f} € ({s['days_elapsed']}/{s['days_in_month']}j)")

    lines.append(f"Semaine :   {s['week_expenses']:>9.2f} € {s['delta_week']}")

    if s["by_category"]:
        lines.append("")
        lines.append("Top dépenses :")
        for cat, total in s["by_category"].items():
            lines.append(f"  {cat:<12} {total:>8.2f} €")

    if s["charges_list"]:
        lines.append("")
        lines.append("Charges fixes :")
        for c in s["charges_list"]:
            lines.append(f"  {c['name']:<12} {c['amount']:>7.2f} €/{c['frequency'][:3]}")

    if s["accounts"]:
        lines.append("")
        lines.append("Comptes :")
        total_balance = sum(a["balance"] for a in s["accounts"])
        for a in s["accounts"]:
            lines.append(f"  {a['name']:<12} {a['balance']:>8.2f} €")
        if len(s["accounts"]) > 1:
            lines.append(f"  TOTAL        {total_balance:>8.2f} €")

    return lines


# ── Menu principal ───────────────────────────────────────────────────────────

async def btn_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "🏠 MENU PRINCIPAL\n\nChoisis une section :",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Sous-menu Finances ───────────────────────────────────────────────────────

async def btn_finance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "💰 FINANCES",
        reply_markup=FINANCE_KEYBOARD,
    )
    return WAITING_FINANCE_MENU


async def receive_finance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_EXPENSE:
        await update.message.reply_text("💸 Montant de la dépense ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_EXPENSE_AMOUNT

    if raw == BTN_INCOME:
        await update.message.reply_text("💰 Montant du revenu ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_INCOME_AMOUNT

    if raw == BTN_CASH:
        accounts = get_accounts()
        if not accounts:
            await update.message.reply_text("Aucun compte trouvé.", reply_markup=FINANCE_KEYBOARD)
        else:
            total = sum(float(a["balance"]) for a in accounts)
            lines = ["💳 SOLDES", ""]
            for a in accounts:
                lines.append(f"{a['name']:<12} {float(a['balance']):>8.2f} €")
            if len(accounts) > 1:
                lines.append("")
                lines.append(f"{'TOTAL':<12} {total:>8.2f} €")
            await update.message.reply_text(_code_block("\n".join(lines)), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=FINANCE_KEYBOARD)
        return WAITING_FINANCE_MENU

    if raw == BTN_CHARGES:
        await update.message.reply_text(_format_charges_display(), reply_markup=FINANCE_KEYBOARD)
        return WAITING_FINANCE_MENU

    if raw == BTN_HISTORY:
        await update.message.reply_text(_format_finance_history(), reply_markup=FINANCE_KEYBOARD)
        return WAITING_FINANCE_MENU

    if raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Sous-menu Tâches ─────────────────────────────────────────────────────────

async def btn_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "✅ TÂCHES",
        reply_markup=TASKS_KEYBOARD,
    )
    return WAITING_TASKS_MENU


async def receive_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_TASK:
        await update.message.reply_text("📝 Description de la tâche ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_TASK

    if raw == BTN_TODAY:
        tasks = get_pending_tasks()
        if not tasks:
            await update.message.reply_text("✨ Aucune tâche en cours !", reply_markup=TASKS_KEYBOARD)
        else:
            await update.message.reply_text(_format_tasks_report(tasks, "📋 MES TÂCHES"), reply_markup=TASKS_KEYBOARD)
        return WAITING_TASKS_MENU

    if raw == BTN_TASK_DONE:
        tasks = get_pending_tasks()
        if not tasks:
            await update.message.reply_text("✨ Aucune tâche en cours !", reply_markup=TASKS_KEYBOARD)
            return WAITING_TASKS_MENU
        rows = [[f"{t['id']}. {t['description']}"] for t in tasks]
        rows.append([BTN_BACK])
        await update.message.reply_text("Quelle tâche terminer ?", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
        return WAITING_DONE_SELECT

    if raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Sous-menu Gestion ────────────────────────────────────────────────────────

async def btn_gestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "⚙️ GESTION",
        reply_markup=GESTION_KEYBOARD,
    )
    return WAITING_GESTION_MENU


async def receive_gestion_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_ACCOUNTS:
        await update.message.reply_text("🏦 Comptes", reply_markup=ACCOUNTS_KEYBOARD)
        return WAITING_ACCOUNTS_MENU

    if raw == BTN_PROJECTS:
        await update.message.reply_text("🗂 Projets", reply_markup=PROJECTS_KEYBOARD)
        return WAITING_PROJECTS_MENU

    if raw == BTN_NEW_CHARGE:
        await update.message.reply_text("📦 Nom de la charge ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_CHARGE_NAME

    if raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Résumé ───────────────────────────────────────────────────────────────────

async def btn_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    from datetime import date as _date
    today = _date.today()
    s = await asyncio.to_thread(get_monthly_summary, today.year, today.month)
    lines = _build_summary_lines(s, today.month, today.year)
    await update.message.reply_text(_code_block("\n".join(lines)), parse_mode=ParseMode.MARKDOWN_V2, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Dépense ──────────────────────────────────────────────────────────────────

async def receive_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Réessaie.")
        return WAITING_EXPENSE_AMOUNT
    if amount <= 0:
        await update.message.reply_text("❌ Le montant doit être positif.")
        return WAITING_EXPENSE_AMOUNT
    context.user_data["expense_amount"] = amount
    await update.message.reply_text("🏷 Catégorie ?", reply_markup=_category_keyboard())
    return WAITING_EXPENSE_CATEGORY


async def receive_expense_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["expense_category"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("🏦 Compte ?", reply_markup=_account_keyboard())
    return WAITING_EXPENSE_ACCOUNT


async def receive_expense_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["expense_account"] = _resolve_account(update.message.text.strip())
    await update.message.reply_text("📅 Date ?", reply_markup=DATE_KEYBOARD)
    return WAITING_EXPENSE_DATE


async def receive_expense_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisis la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_EXPENSE_DATE_INPUT
    if raw == BTN_SKIP:
        return await _finalize_expense(update, context, None)
    d = parse_date(raw)
    return await _finalize_expense(update, context, d)


async def receive_expense_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("❌ Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_EXPENSE_DATE_INPUT
    return await _finalize_expense(update, context, d)


async def _finalize_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, d: Date | None) -> int:
    amount = context.user_data.pop("expense_amount")
    category = context.user_data.pop("expense_category")
    account_name = context.user_data.pop("expense_account", None)
    insert_expense(amount, "", category, account_name, d)
    msg = _format_confirmation("expense", amount, category, account_name, d)
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Revenu ───────────────────────────────────────────────────────────────────

async def receive_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Réessaie.")
        return WAITING_INCOME_AMOUNT
    if amount <= 0:
        await update.message.reply_text("❌ Le montant doit être positif.")
        return WAITING_INCOME_AMOUNT
    context.user_data["income_amount"] = amount
    await update.message.reply_text("🏷 Catégorie ?", reply_markup=_category_keyboard())
    return WAITING_INCOME_CATEGORY


async def receive_income_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["income_category"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("🏦 Compte ?", reply_markup=_account_keyboard())
    return WAITING_INCOME_ACCOUNT


async def receive_income_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["income_account"] = _resolve_account(update.message.text.strip())
    await update.message.reply_text("🗂 Projet ? (optionnel)", reply_markup=_project_keyboard())
    return WAITING_INCOME_PROJECT


async def receive_income_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["income_project"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("📅 Date ?", reply_markup=DATE_KEYBOARD)
    return WAITING_INCOME_DATE


async def receive_income_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisis la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_INCOME_DATE_INPUT
    if raw == BTN_SKIP:
        return await _finalize_income(update, context, None)
    d = parse_date(raw)
    return await _finalize_income(update, context, d)


async def receive_income_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("❌ Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_INCOME_DATE_INPUT
    return await _finalize_income(update, context, d)


async def _finalize_income(update: Update, context: ContextTypes.DEFAULT_TYPE, d: Date | None) -> int:
    amount = context.user_data.pop("income_amount")
    category = context.user_data.pop("income_category")
    account_name = context.user_data.pop("income_account", None)
    project_name = context.user_data.pop("income_project", None)
    insert_income(amount, "", category, account_name, d, project_name)
    msg = _format_confirmation("income", amount, category, account_name, d)
    if project_name:
        msg += f" · {project_name}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Terminer tâche ───────────────────────────────────────────────────────────

async def receive_done_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    try:
        task_id = int(raw.split(".")[0])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Sélection invalide.")
        return WAITING_DONE_SELECT
    if mark_done(task_id):
        await update.message.reply_text("✅ Tâche terminée !", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("❌ Tâche introuvable ou déjà terminée.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Nouvelle tâche ───────────────────────────────────────────────────────────

async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["task_desc"] = update.message.text.strip()
    await update.message.reply_text("🗂 Projet ? (optionnel)", reply_markup=_project_keyboard())
    return WAITING_TASK_PROJECT


async def receive_task_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["task_project"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("📅 Date d'échéance ?", reply_markup=DATE_KEYBOARD)
    return WAITING_TASK_DUE


async def receive_task_due(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisis la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_TASK_DUE_INPUT
    if raw == BTN_SKIP:
        return await _finalize_task(update, context, None)
    d = parse_date(raw)
    return await _finalize_task(update, context, d)


async def receive_task_due_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("❌ Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_TASK_DUE_INPUT
    return await _finalize_task(update, context, d)


async def _finalize_task(update: Update, context: ContextTypes.DEFAULT_TYPE, due_date) -> int:
    from app.core.projects import get_project_id
    description = context.user_data.pop("task_desc")
    project_raw = context.user_data.pop("task_project", None)
    project_id = get_project_id(project_raw) if project_raw else None
    insert_task(description, due_date, project_id)
    msg = f"✅ Tâche ajoutée : {description}"
    if project_raw:
        msg += f" 〔{project_raw}〕"
    if due_date:
        msg += f" — 📅 {due_date.strftime('%d/%m/%Y')}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Charges ──────────────────────────────────────────────────────────────────

async def receive_charge_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    context.user_data["charge_name"] = raw
    await update.message.reply_text("💶 Montant ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_CHARGE_AMOUNT


async def receive_charge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Montant invalide.")
        return WAITING_CHARGE_AMOUNT
    if amount <= 0:
        await update.message.reply_text("❌ Le montant doit être positif.")
        return WAITING_CHARGE_AMOUNT
    context.user_data["charge_amount"] = amount
    await update.message.reply_text("🔄 Fréquence ?", reply_markup=FREQ_KEYBOARD)
    return WAITING_CHARGE_FREQ


async def receive_charge_freq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    freq = update.message.text.strip()
    if freq not in ("Mensuel", "Annuel"):
        await update.message.reply_text("Choisis Mensuel ou Annuel.", reply_markup=FREQ_KEYBOARD)
        return WAITING_CHARGE_FREQ
    context.user_data["charge_freq"] = freq
    await update.message.reply_text("🏦 Compte ?", reply_markup=_account_keyboard())
    return WAITING_CHARGE_ACCOUNT


async def receive_charge_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    account_name = _resolve_account(update.message.text.strip())
    name = context.user_data.pop("charge_name")
    amount = context.user_data.pop("charge_amount")
    freq = context.user_data.pop("charge_freq")
    insert_charge(name, amount, freq, account_name)
    msg = f"✅ Charge ajoutée : {name} — {amount:.2f} € / {freq}"
    if account_name:
        msg += f" · {account_name}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Comptes ──────────────────────────────────────────────────────────────────

async def receive_accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_ACCOUNT:
        await update.message.reply_text("🏦 Nom du compte ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_ACCOUNT_NAME

    if raw == BTN_ACCOUNTS_BALANCE:
        accounts = get_accounts()
        if not accounts:
            await update.message.reply_text("Aucun compte trouvé.", reply_markup=GESTION_KEYBOARD)
        else:
            lines = [f"  {a['name']} : {float(a['balance']):.2f} €" for a in accounts]
            await update.message.reply_text("🏦 Soldes\n\n" + "\n".join(lines), reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    if raw == BTN_BACK:
        await update.message.reply_text("⚙️ Gestion", reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    await update.message.reply_text("⚙️ Gestion", reply_markup=GESTION_KEYBOARD)
    return WAITING_GESTION_MENU


async def receive_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    context.user_data["account_name"] = raw
    await update.message.reply_text("💶 Solde initial (0 si vide) ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_ACCOUNT_BALANCE


async def receive_account_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        balance = float(text.replace(",", ".")) if text else 0.0
    except ValueError:
        await update.message.reply_text("❌ Montant invalide (ou tape 0).")
        return WAITING_ACCOUNT_BALANCE
    name = context.user_data.pop("account_name")
    insert_account(name, balance)
    await update.message.reply_text(f"✅ Compte créé : {name} — {balance:.2f} €", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Projets ──────────────────────────────────────────────────────────────────

async def receive_projects_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_PROJECT:
        await update.message.reply_text("🗂 Nom du projet ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_PROJECT_NAME

    if raw == BTN_PROJECTS_LIST:
        summaries = await asyncio.to_thread(get_projects_with_summary)
        if not summaries:
            await update.message.reply_text("Aucun projet.", reply_markup=GESTION_KEYBOARD)
        else:
            lines = [f"  {s['name']} — {s['total']:.2f} € ({s['count']} revenus)" for s in summaries]
            await update.message.reply_text("🗂 Projets\n\n" + "\n".join(lines), reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    if raw == BTN_BACK:
        await update.message.reply_text("⚙️ Gestion", reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    await update.message.reply_text("⚙️ Gestion", reply_markup=GESTION_KEYBOARD)
    return WAITING_GESTION_MENU


async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text("🏠 Menu principal", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    insert_project(raw.upper())
    await update.message.reply_text(f"✅ Projet créé : {raw.upper()}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Annulation / expiration ──────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Annulé.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏰ Session expirée (inactivité). On repart du menu principal.",
            reply_markup=MAIN_KEYBOARD,
        )


# ── Construction du handler ──────────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    btn_filter = filters.TEXT & ~filters.COMMAND
    nav = [
        MessageHandler(filters.Regex(f"^{BTN_FINANCE.replace('(', '.').replace(')', '.')}$"), btn_finance),
        MessageHandler(filters.Regex(f"^{BTN_TASKS.replace('(', '.').replace(')', '.')}$"), btn_tasks),
        MessageHandler(filters.Regex(f"^{BTN_GESTION.replace('(', '.').replace(')', '.')}$"), btn_gestion),
        MessageHandler(filters.Regex(f"^{BTN_SUMMARY.replace('(', '.').replace(')', '.')}$"), btn_summary),
    ]
    return ConversationHandler(
        entry_points=nav,
        states={
            WAITING_FINANCE_MENU:       nav + [MessageHandler(btn_filter, receive_finance_menu)],
            WAITING_TASKS_MENU:         nav + [MessageHandler(btn_filter, receive_tasks_menu)],
            WAITING_GESTION_MENU:       nav + [MessageHandler(btn_filter, receive_gestion_menu)],
            WAITING_ACCOUNTS_MENU:      nav + [MessageHandler(btn_filter, receive_accounts_menu)],
            WAITING_PROJECTS_MENU:      nav + [MessageHandler(btn_filter, receive_projects_menu)],
            WAITING_EXPENSE_AMOUNT:     nav + [MessageHandler(btn_filter, receive_expense_amount)],
            WAITING_EXPENSE_CATEGORY:   nav + [MessageHandler(btn_filter, receive_expense_category)],
            WAITING_EXPENSE_ACCOUNT:    nav + [MessageHandler(btn_filter, receive_expense_account)],
            WAITING_EXPENSE_DATE:       nav + [MessageHandler(btn_filter, receive_expense_date)],
            WAITING_EXPENSE_DATE_INPUT: nav + [MessageHandler(btn_filter, receive_expense_date_input)],
            WAITING_INCOME_AMOUNT:      nav + [MessageHandler(btn_filter, receive_income_amount)],
            WAITING_INCOME_CATEGORY:    nav + [MessageHandler(btn_filter, receive_income_category)],
            WAITING_INCOME_ACCOUNT:     nav + [MessageHandler(btn_filter, receive_income_account)],
            WAITING_INCOME_PROJECT:     nav + [MessageHandler(btn_filter, receive_income_project)],
            WAITING_INCOME_DATE:        nav + [MessageHandler(btn_filter, receive_income_date)],
            WAITING_INCOME_DATE_INPUT:  nav + [MessageHandler(btn_filter, receive_income_date_input)],
            WAITING_TASK:               nav + [MessageHandler(btn_filter, receive_task)],
            WAITING_TASK_PROJECT:       nav + [MessageHandler(btn_filter, receive_task_project)],
            WAITING_TASK_DUE:           nav + [MessageHandler(btn_filter, receive_task_due)],
            WAITING_TASK_DUE_INPUT:     nav + [MessageHandler(btn_filter, receive_task_due_input)],
            WAITING_DONE_SELECT:        nav + [MessageHandler(btn_filter, receive_done_select)],
            WAITING_CHARGE_NAME:        nav + [MessageHandler(btn_filter, receive_charge_name)],
            WAITING_CHARGE_AMOUNT:      nav + [MessageHandler(btn_filter, receive_charge_amount)],
            WAITING_CHARGE_FREQ:        nav + [MessageHandler(btn_filter, receive_charge_freq)],
            WAITING_CHARGE_ACCOUNT:     nav + [MessageHandler(btn_filter, receive_charge_account)],
            WAITING_ACCOUNT_NAME:       nav + [MessageHandler(btn_filter, receive_account_name)],
            WAITING_ACCOUNT_BALANCE:    nav + [MessageHandler(btn_filter, receive_account_balance)],
            WAITING_PROJECT_NAME:       nav + [MessageHandler(btn_filter, receive_project_name)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, conversation_timeout)],
        },
        fallbacks=[
            CommandHandler("annuler", cancel),
            CommandHandler("cancel", cancel),
        ],
        conversation_timeout=600,
        per_user=True,
        per_chat=True,
    )
