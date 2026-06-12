from datetime import date as Date
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
from app.core.config import TELEGRAM_ALLOWED_USER_ID
from app.core.expenses import insert_expense
from app.core.incomes import insert_income
from app.core.tasks import insert_task, get_pending_tasks, mark_done, get_tasks_due_tomorrow
from app.core.accounts import get_accounts, get_default_account, insert_account
from app.core.utils import CATEGORIES, parse_date
from app.core.reporting import get_monthly_summary
from app.core.charges import insert_charge, get_charges
from app.core.projects import insert_project, get_projects, get_project_summary

BTN_EXPENSE = "💸 Dépense"
BTN_INCOME = "💰 Revenu"
BTN_TASK = "✅ Tâche"
BTN_TODAY = "📋 Mes tâches"
BTN_DONE = "☑️ Terminer"
BTN_CASH = "💳 Cash"
BTN_SKIP = "Passer"
BTN_SUMMARY = "📊 Résumé"
BTN_CHARGES = "📦 Charges"
BTN_NEW_CHARGE = "Nouvelle charge"
BTN_PROJECTS = "🗂 Projets"
BTN_NEW_PROJECT = "Nouveau projet"
BTN_ACCOUNTS = "🏦 Comptes"
BTN_NEW_ACCOUNT = "Nouveau compte"
BTN_TODAY_DATE = "Aujourd'hui"
BTN_YESTERDAY = "Hier"
BTN_CUSTOM_DATE = "Saisir une date"

(
    WAITING_EXPENSE_AMOUNT,
    WAITING_EXPENSE_DESC,
    WAITING_EXPENSE_CATEGORY,
    WAITING_EXPENSE_ACCOUNT,
    WAITING_EXPENSE_DATE,
    WAITING_EXPENSE_DATE_INPUT,
    WAITING_INCOME_AMOUNT,
    WAITING_INCOME_DESC,
    WAITING_INCOME_CATEGORY,
    WAITING_INCOME_ACCOUNT,
    WAITING_INCOME_DATE,
    WAITING_INCOME_DATE_INPUT,
    WAITING_TASK,
    WAITING_DONE_SELECT,
    WAITING_CHARGE_NAME,
    WAITING_CHARGE_AMOUNT,
    WAITING_CHARGE_FREQ,
    WAITING_INCOME_PROJECT,
    WAITING_PROJECT_NAME,
    WAITING_CHARGE_ACCOUNT,
    WAITING_ACCOUNT_NAME,
    WAITING_ACCOUNT_BALANCE,
    WAITING_TASK_PROJECT,
    WAITING_TASK_DUE,
    WAITING_TASK_DUE_INPUT,
) = range(25)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_EXPENSE, BTN_INCOME],
        [BTN_CHARGES, BTN_PROJECTS],
        [BTN_TASK, BTN_TODAY],
        [BTN_DONE, BTN_SUMMARY],
        [BTN_ACCOUNTS],
    ],
    resize_keyboard=True,
)

FREQ_KEYBOARD = ReplyKeyboardMarkup(
    [["Mensuel", "Annuel"]],
    resize_keyboard=True,
)

DATE_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_TODAY_DATE, BTN_YESTERDAY], [BTN_CUSTOM_DATE]],
    resize_keyboard=True,
)


def _allowed(update: Update) -> bool:
    return update.effective_user.id == TELEGRAM_ALLOWED_USER_ID


def _project_keyboard() -> ReplyKeyboardMarkup:
    projects = get_projects()
    rows = [[p["name"]] for p in projects]
    rows.append([BTN_NEW_PROJECT, BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _account_keyboard() -> ReplyKeyboardMarkup:
    accounts = get_accounts()
    rows = [[a["name"]] for a in accounts]
    default = get_default_account()
    label = f"Passer (→ {default})" if default else "Passer"
    rows.append([label])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _resolve_account(raw: str) -> str | None:
    if raw.startswith("Passer"):
        return get_default_account()
    return raw.lower()


def _category_keyboard() -> ReplyKeyboardMarkup:
    rows = [[CATEGORIES[i], CATEGORIES[i + 1]] for i in range(0, len(CATEGORIES) - 1, 2)]
    rows.append([BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _format_confirmation(kind: str, amount: float, description: str, category: str | None, account_raw: str | None, d: Date | None) -> str:
    parts = [f"{amount:.2f} €", description]
    if category:
        parts.append(category)
    if account_raw and account_raw != BTN_SKIP:
        parts.append(account_raw)
    if d:
        parts.append(d.strftime("%d/%m/%Y"))
    label = "Dépense" if kind == "expense" else "Revenu"
    return f"{label} enregistré{'e' if kind == 'expense' else ''} : " + " | ".join(parts)


# ── Entry points ──────────────────────────────────────────────────────────────

async def btn_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("Montant ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_EXPENSE_AMOUNT


async def btn_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("Montant ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_INCOME_AMOUNT


async def btn_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("Description de la tâche ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_TASK


def _format_tasks(tasks: list) -> str:
    from datetime import date as _date
    today = _date.today()
    lines = []
    for t in tasks:
        line = f"{t['id']}. {t['description']}"
        if t.get("project_name"):
            line += f" [{t['project_name']}]"
        if t.get("due_date"):
            due = _date.fromisoformat(t["due_date"])
            delta = (due - today).days
            if delta < 0:
                line += f" ⚠️ en retard ({due.strftime('%d/%m')})"
            elif delta == 0:
                line += f" 🔴 aujourd'hui"
            elif delta == 1:
                line += f" 🟡 demain"
            else:
                line += f" 📅 {due.strftime('%d/%m')}"
        lines.append(line)
    return "\n".join(lines)


async def btn_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    tasks = get_pending_tasks()
    if not tasks:
        await update.message.reply_text("Aucune tâche en cours.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(_format_tasks(tasks), reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def btn_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    tasks = get_pending_tasks()
    if not tasks:
        await update.message.reply_text("Aucune tâche en cours.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    rows = [[f"{t['id']}. {t['description']}"] for t in tasks]
    rows.append([BTN_SKIP])
    await update.message.reply_text("Quelle tâche terminer ?", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
    return WAITING_DONE_SELECT


def _build_summary_lines(s: dict, month: int, year: int) -> list[str]:
    import calendar
    month_name = calendar.month_name[month].capitalize()
    sign = "+" if s["cashflow"] >= 0 else ""
    lines = [
        f"📊 {month_name} {year}",
        "",
        f"💰 Revenus   : {s['incomes']:.2f} €{s['delta_incomes']}",
        f"💸 Dépenses  : {s['expenses']:.2f} €{s['delta_expenses']}",
        f"📦 Charges   : {s['charges']:.2f} €",
        f"{'✅' if s['cashflow'] >= 0 else '⚠️'} Cashflow  : {sign}{s['cashflow']:.2f} €{s['delta_cashflow']}",
    ]

    # Projection fin de mois
    if s.get("projection") is not None:
        lines.append(f"📈 Projection : {s['projection']:.2f} € dépenses ({s['days_elapsed']}/{s['days_in_month']} jours)")

    # Semaine courante
    lines.append("")
    lines.append(f"📅 Cette semaine : {s['week_expenses']:.2f} €{s['delta_week']} vs semaine préc.")

    # Top catégories
    if s["by_category"]:
        lines.append("")
        lines.append("Top dépenses :")
        for cat, total in s["by_category"].items():
            lines.append(f"  {cat} : {total:.2f} €")

    # Charges récurrentes
    if s["charges_list"]:
        lines.append("")
        lines.append("Charges fixes :")
        for c in s["charges_list"]:
            lines.append(f"  {c['name']} : {c['amount']:.2f} € / {c['frequency']}")

    # Comptes
    if s["accounts"]:
        lines.append("")
        lines.append("🏦 Comptes :")
        total_balance = sum(a["balance"] for a in s["accounts"])
        for a in s["accounts"]:
            lines.append(f"  {a['name']} : {a['balance']:.2f} €")
        if len(s["accounts"]) > 1:
            lines.append(f"  Total : {total_balance:.2f} €")

    return lines


async def btn_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    from datetime import date as _date
    today = _date.today()
    s = get_monthly_summary(today.year, today.month)
    lines = _build_summary_lines(s, today.month, today.year)
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def btn_cash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    accounts = get_accounts()
    if not accounts:
        await update.message.reply_text("Aucun compte trouvé.", reply_markup=MAIN_KEYBOARD)
    else:
        lines = [f"{a['name']} : {a['balance']:.2f} €" for a in accounts]
        await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Dépense ───────────────────────────────────────────────────────────────────

async def receive_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Montant invalide. Réessaie.")
        return WAITING_EXPENSE_AMOUNT
    if amount <= 0:
        await update.message.reply_text("Le montant doit être positif. Réessaie.")
        return WAITING_EXPENSE_AMOUNT
    context.user_data["expense_amount"] = amount
    await update.message.reply_text("Description ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_EXPENSE_DESC


async def receive_expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["expense_desc"] = update.message.text.strip()
    await update.message.reply_text("Catégorie ?", reply_markup=_category_keyboard())
    return WAITING_EXPENSE_CATEGORY


async def receive_expense_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["expense_category"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("Compte ?", reply_markup=_account_keyboard())
    return WAITING_EXPENSE_ACCOUNT


async def receive_expense_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["expense_account"] = _resolve_account(update.message.text.strip())
    await update.message.reply_text("Date ?", reply_markup=DATE_KEYBOARD)
    return WAITING_EXPENSE_DATE


async def receive_expense_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisir la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_EXPENSE_DATE_INPUT
    d = parse_date(raw)
    return await _finalize_expense(update, context, d)


async def receive_expense_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_EXPENSE_DATE_INPUT
    return await _finalize_expense(update, context, d)


async def _finalize_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, d: Date | None) -> int:
    amount = context.user_data.pop("expense_amount")
    description = context.user_data.pop("expense_desc")
    category = context.user_data.pop("expense_category")
    account_name = context.user_data.pop("expense_account", None)
    insert_expense(amount, description, category, account_name, d)
    msg = _format_confirmation("expense", amount, description, category, account_name, d)
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Revenu ────────────────────────────────────────────────────────────────────

async def receive_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Montant invalide. Réessaie.")
        return WAITING_INCOME_AMOUNT
    if amount <= 0:
        await update.message.reply_text("Le montant doit être positif. Réessaie.")
        return WAITING_INCOME_AMOUNT
    context.user_data["income_amount"] = amount
    await update.message.reply_text("Description ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_INCOME_DESC


async def receive_income_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["income_desc"] = update.message.text.strip()
    await update.message.reply_text("Catégorie ?", reply_markup=_category_keyboard())
    return WAITING_INCOME_CATEGORY


async def receive_income_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["income_category"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("Compte ?", reply_markup=_account_keyboard())
    return WAITING_INCOME_ACCOUNT


async def receive_income_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["income_account"] = _resolve_account(update.message.text.strip())
    await update.message.reply_text("Projet ? (optionnel)", reply_markup=_project_keyboard())
    return WAITING_INCOME_PROJECT


async def receive_income_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["income_project"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("Date ?", reply_markup=DATE_KEYBOARD)
    return WAITING_INCOME_DATE


async def receive_income_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisir la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_INCOME_DATE_INPUT
    d = parse_date(raw)
    return await _finalize_income(update, context, d)


async def receive_income_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_INCOME_DATE_INPUT
    return await _finalize_income(update, context, d)


async def _finalize_income(update: Update, context: ContextTypes.DEFAULT_TYPE, d: Date | None) -> int:
    amount = context.user_data.pop("income_amount")
    description = context.user_data.pop("income_desc")
    category = context.user_data.pop("income_category")
    account_name = context.user_data.pop("income_account", None)
    project_name = context.user_data.pop("income_project", None)
    insert_income(amount, description, category, account_name, d, project_name)
    msg = _format_confirmation("income", amount, description, category, account_name, d)
    if project_name:
        msg += f" | {project_name}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Terminer une tâche ────────────────────────────────────────────────────────

async def receive_done_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP:
        await update.message.reply_text("Annulé.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    try:
        task_id = int(raw.split(".")[0])
    except (ValueError, IndexError):
        await update.message.reply_text("Sélection invalide. Réessaie.")
        return WAITING_DONE_SELECT
    if mark_done(task_id):
        await update.message.reply_text("Tâche terminée ✓", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("Tâche introuvable ou déjà terminée.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Tâche ─────────────────────────────────────────────────────────────────────

async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["task_desc"] = update.message.text.strip()
    await update.message.reply_text("Projet ? (optionnel)", reply_markup=_project_keyboard())
    return WAITING_TASK_PROJECT


async def receive_task_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    context.user_data["task_project"] = None if raw == BTN_SKIP else raw
    await update.message.reply_text("Date d'échéance ?", reply_markup=DATE_KEYBOARD)
    return WAITING_TASK_DUE


async def receive_task_due(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_CUSTOM_DATE:
        await update.message.reply_text("Saisir la date (ex: 02/06/2026 ou 02/06) :", reply_markup=MAIN_KEYBOARD)
        return WAITING_TASK_DUE_INPUT
    d = parse_date(raw)
    return await _finalize_task(update, context, d)


async def receive_task_due_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = parse_date(update.message.text.strip())
    if d is None:
        await update.message.reply_text("Format invalide. Essaie : 02/06/2026 ou 02/06")
        return WAITING_TASK_DUE_INPUT
    return await _finalize_task(update, context, d)


async def _finalize_task(update: Update, context: ContextTypes.DEFAULT_TYPE, due_date) -> int:
    from app.core.projects import get_project_id
    description = context.user_data.pop("task_desc")
    project_raw = context.user_data.pop("task_project", None)
    project_id = get_project_id(project_raw) if project_raw else None
    insert_task(description, due_date, project_id)
    msg = f"Tâche ajoutée : {description}"
    if project_raw:
        msg += f" [{project_raw}]"
    if due_date:
        msg += f" — échéance {due_date.strftime('%d/%m/%Y')}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Charges ──────────────────────────────────────────────────────────────────

async def btn_charges(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    charges = get_charges()
    if charges:
        lines = [f"{c['name']} : {float(c['amount']):.2f} € / {c['frequency']}" for c in charges]
        lines.append("")
        lines.append("— Nouvelle charge ?")
        text = "\n".join(lines)
    else:
        text = "Aucune charge. Créer la première ?"
    keyboard = ReplyKeyboardMarkup([[BTN_NEW_CHARGE], [BTN_SKIP]], resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=keyboard)
    return WAITING_CHARGE_NAME


async def receive_charge_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP:
        await update.message.reply_text("Annulé.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    if raw == BTN_NEW_CHARGE:
        await update.message.reply_text("Nom de la charge ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_CHARGE_NAME
    context.user_data["charge_name"] = raw
    await update.message.reply_text("Montant ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_CHARGE_AMOUNT


async def receive_charge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Montant invalide. Réessaie.")
        return WAITING_CHARGE_AMOUNT
    if amount <= 0:
        await update.message.reply_text("Le montant doit être positif. Réessaie.")
        return WAITING_CHARGE_AMOUNT
    context.user_data["charge_amount"] = amount
    await update.message.reply_text("Fréquence ?", reply_markup=FREQ_KEYBOARD)
    return WAITING_CHARGE_FREQ


async def receive_charge_freq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    freq = update.message.text.strip()
    if freq not in ("Mensuel", "Annuel"):
        await update.message.reply_text("Choisis Mensuel ou Annuel.", reply_markup=FREQ_KEYBOARD)
        return WAITING_CHARGE_FREQ
    context.user_data["charge_freq"] = freq
    await update.message.reply_text("Compte ?", reply_markup=_account_keyboard())
    return WAITING_CHARGE_ACCOUNT


async def receive_charge_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    account_name = _resolve_account(update.message.text.strip())
    name = context.user_data.pop("charge_name")
    amount = context.user_data.pop("charge_amount")
    freq = context.user_data.pop("charge_freq")
    insert_charge(name, amount, freq, account_name)
    msg = f"Charge ajoutée : {name} — {amount:.2f} € / {freq}"
    if account_name:
        msg += f" | {account_name}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Comptes ───────────────────────────────────────────────────────────────────

async def btn_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    accounts = get_accounts()
    if accounts:
        lines = [f"{a['name']} : {float(a['balance']):.2f} €" for a in accounts]
        lines.append("")
        lines.append("— Nouveau compte ?")
        text = "\n".join(lines)
    else:
        text = "Aucun compte. Créer le premier ?"
    keyboard = ReplyKeyboardMarkup([[BTN_NEW_ACCOUNT], [BTN_SKIP]], resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=keyboard)
    return WAITING_ACCOUNT_NAME


async def receive_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP:
        await update.message.reply_text("Annulé.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    if raw == BTN_NEW_ACCOUNT:
        await update.message.reply_text("Nom du compte ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_ACCOUNT_NAME
    context.user_data["account_name"] = raw
    await update.message.reply_text("Solde initial (0 si vide) ?", reply_markup=MAIN_KEYBOARD)
    return WAITING_ACCOUNT_BALANCE


async def receive_account_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        balance = float(text.replace(",", ".")) if text else 0.0
    except ValueError:
        await update.message.reply_text("Montant invalide. Réessaie (ou tape 0).")
        return WAITING_ACCOUNT_BALANCE
    name = context.user_data.pop("account_name")
    insert_account(name, balance)
    await update.message.reply_text(f"Compte créé : {name} — {balance:.2f} €", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Projets ───────────────────────────────────────────────────────────────────

async def btn_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    projects = get_projects()
    if projects:
        lines = []
        for p in projects:
            s = get_project_summary(p["name"])
            lines.append(f"{p['name']} : {s['total']:.2f} € ({s['count']} revenus)")
        lines.append("")
        lines.append("— Nouveau projet ?")
        text = "\n".join(lines)
    else:
        text = "Aucun projet. Créer le premier ?"
    keyboard = ReplyKeyboardMarkup([[BTN_NEW_PROJECT], [BTN_SKIP]], resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=keyboard)
    return WAITING_PROJECT_NAME


async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP:
        await update.message.reply_text("Annulé.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    if raw == BTN_NEW_PROJECT:
        await update.message.reply_text("Nom du projet ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_PROJECT_NAME
    insert_project(raw.upper())
    await update.message.reply_text(f"Projet créé : {raw.upper()}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Construction du handler ───────────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    btn_filter = filters.TEXT & ~filters.COMMAND
    nav = [
        MessageHandler(filters.Regex(f"^{BTN_EXPENSE}$"), btn_expense),
        MessageHandler(filters.Regex(f"^{BTN_INCOME}$"), btn_income),
        MessageHandler(filters.Regex(f"^{BTN_TASK}$"), btn_task),
        MessageHandler(filters.Regex(f"^{BTN_TODAY}$"), btn_today),
        MessageHandler(filters.Regex(f"^{BTN_DONE}$"), btn_done),
        MessageHandler(filters.Regex(f"^{BTN_CASH}$"), btn_cash),
        MessageHandler(filters.Regex(f"^{BTN_SUMMARY}$"), btn_summary),
        MessageHandler(filters.Regex(f"^{BTN_CHARGES}$"), btn_charges),
        MessageHandler(filters.Regex(f"^{BTN_PROJECTS}$"), btn_projects),
        MessageHandler(filters.Regex(f"^{BTN_ACCOUNTS}$"), btn_accounts),
    ]
    return ConversationHandler(
        entry_points=nav,
        states={
            WAITING_EXPENSE_AMOUNT:     nav + [MessageHandler(btn_filter, receive_expense_amount)],
            WAITING_EXPENSE_DESC:       nav + [MessageHandler(btn_filter, receive_expense_desc)],
            WAITING_EXPENSE_CATEGORY:   nav + [MessageHandler(btn_filter, receive_expense_category)],
            WAITING_EXPENSE_ACCOUNT:    nav + [MessageHandler(btn_filter, receive_expense_account)],
            WAITING_EXPENSE_DATE:       nav + [MessageHandler(btn_filter, receive_expense_date)],
            WAITING_EXPENSE_DATE_INPUT: nav + [MessageHandler(btn_filter, receive_expense_date_input)],
            WAITING_INCOME_AMOUNT:      nav + [MessageHandler(btn_filter, receive_income_amount)],
            WAITING_INCOME_DESC:        nav + [MessageHandler(btn_filter, receive_income_desc)],
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
            WAITING_PROJECT_NAME:       nav + [MessageHandler(btn_filter, receive_project_name)],
            WAITING_ACCOUNT_NAME:       nav + [MessageHandler(btn_filter, receive_account_name)],
            WAITING_ACCOUNT_BALANCE:    nav + [MessageHandler(btn_filter, receive_account_balance)],
        },
        fallbacks=[],
        per_user=True,
        per_chat=True,
    )
