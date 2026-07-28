from datetime import date as Date
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
from app.core.config import TELEGRAM_ALLOWED_USER_ID
from app.core.expenses import insert_expense, get_recent_expenses
from app.core.incomes import insert_income, get_recent_incomes
from app.core.tasks import insert_task, get_pending_tasks, mark_done, get_tasks_due_tomorrow
from app.core.accounts import get_accounts, get_default_account, insert_account
from app.core.utils import CATEGORIES, parse_date
from app.core.reporting import get_monthly_summary
from app.core.charges import insert_charge, get_charges
from app.core.projects import insert_project, get_projects, get_project_summary
from app.bot.formatting import (
    esc, money, bar, pre, hr, category_bars, accounts_block, charges_block,
    movement_confirmation, task_confirmation,
)

# ── Boutons ──────────────────────────────────────────────────────────────────

BTN_FINANCE = "💰 Finances"
BTN_TASKS = "✅ Tâches"
BTN_GESTION = "⚙️ Gestion"
BTN_SUMMARY = "📊 Résumé du mois"

BTN_EXPENSE = "💸 Dépense"
BTN_INCOME = "💵 Revenu"
BTN_CASH = "💳 Soldes"
BTN_CHARGES = "📦 Charges fixes"

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

MAIN_MENU_TEXT = "<b>🏠 Menu</b>"

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


def _project_keyboard() -> ReplyKeyboardMarkup:
    projects = get_projects()
    rows = [[p["name"]] for p in projects]
    rows.append([BTN_SKIP])
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
    if len(CATEGORIES) % 2:
        rows.append([CATEGORIES[-1]])
    rows.append([BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


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
                badge = "⚪"
        else:
            badge = "⚪"

        line = f"{badge} <b>{t['id']}.</b> {esc(t['description'])}"
        if t.get("project_name"):
            line += f" · {esc(t['project_name'])}"
        if t.get("due_date"):
            due = _date.fromisoformat(t["due_date"])
            delta = (due - today).days
            if delta < 0:
                line += f" — ⚠️ {abs(delta)}j de retard"
            elif delta == 0:
                line += " — aujourd'hui"
            elif delta == 1:
                line += " — demain"
            else:
                line += f" — {due.strftime('%d/%m')}"
        lines.append(line)
    return "\n".join(lines)


def _format_tasks_report(tasks: list, title: str) -> str:
    count = len(tasks)
    header = f"<b>{title}</b> · {count} tâche{'s' if count > 1 else ''}\n\n"
    return header + _format_tasks(tasks)


def _format_charges_display() -> str:
    charges = get_charges()
    if not charges:
        return "<b>📦 Charges fixes</b>\n\nAucune charge enregistrée."
    total_mensuel = sum(
        float(c["amount"]) if c["frequency"] == "Mensuel" else float(c["amount"]) / 12
        for c in charges
    )
    lines = ["<b>📦 Charges fixes</b>", ""]
    for c in charges:
        line = f"• {esc(c['name'])} — {money(float(c['amount']))} / {c['frequency']}"
        if c.get("account_name"):
            line += f" · {esc(c['account_name'])}"
        lines.append(line)
    lines.append("")
    lines.append(pre([
        f"{'Total mensuel':<14} {money(total_mensuel):>13}",
        f"{'Total annuel':<14} {money(total_mensuel * 12):>13}",
    ]))
    lines.append("💡 Quand débitée, enregistre-la en dépense (catégorie « Charges »).")
    return "\n".join(lines)


_MONTH_NAMES_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def _build_summary_lines(s: dict, month: int, year: int) -> list[str]:
    month_name = _MONTH_NAMES_FR[month]

    metric_rows = [
        ("Revenus", s["incomes"], s["delta_incomes"]),
        ("Dépenses", s["expenses"], s["delta_expenses"]),
        ("Charges", s["charges"], ""),
    ]
    table = [f"{label:<9} {money(val):>13} {delta}".rstrip() for label, val, delta in metric_rows]
    table.append(hr(24))
    table.append(f"{'Cashflow':<9} {money(s['cashflow']):>13} {s['delta_cashflow']}".rstrip())

    parts = [
        f"<b>📊 Résumé — {month_name} {year}</b>",
        "",
        pre(table),
    ]

    if s.get("projection") is not None:
        status = "✅" if s["projection"] <= s["incomes"] else "⚠️"
        parts.append(f"{status} Projection fin de mois : <b>{money(s['projection'])}</b> de dépenses")

    if s["days_in_month"]:
        progress = bar(s["days_elapsed"] / s["days_in_month"])
        parts.append(f"{progress}  jour {s['days_elapsed']}/{s['days_in_month']}")

    parts.append(f"📅 Semaine en cours : {money(s['week_expenses'])} {s['delta_week']}".rstrip())

    if s["by_category"]:
        parts.append("")
        parts.append("<b>Top catégories</b>")
        parts.append(pre(category_bars(s["by_category"]).split("\n")))

    if s["charges_list"]:
        parts.append("")
        parts.append("<b>Charges fixes</b>")
        parts.append(charges_block([
            {"name": c["name"], "amount": c["amount"], "frequency": c["frequency"]}
            for c in s["charges_list"]
        ]))

    if s["accounts"]:
        parts.append("")
        parts.append("<b>Comptes</b>")
        parts.append(accounts_block(s["accounts"]))

    return parts


# ── Menu principal ───────────────────────────────────────────────────────────

async def btn_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Sous-menu Finances ───────────────────────────────────────────────────────

async def btn_finance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("<b>💰 Finances</b>", reply_markup=FINANCE_KEYBOARD)
    return WAITING_FINANCE_MENU


async def receive_finance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_EXPENSE:
        await update.message.reply_text("Montant de la dépense ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_EXPENSE_AMOUNT

    if raw == BTN_INCOME:
        await update.message.reply_text("Montant du revenu ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_INCOME_AMOUNT

    if raw == BTN_CASH:
        accounts = get_accounts()
        await update.message.reply_text("<b>💳 Soldes</b>\n\n" + accounts_block(accounts), reply_markup=FINANCE_KEYBOARD)
        return WAITING_FINANCE_MENU

    if raw == BTN_CHARGES:
        await update.message.reply_text(_format_charges_display(), reply_markup=FINANCE_KEYBOARD)
        return WAITING_FINANCE_MENU

    if raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Sous-menu Tâches ─────────────────────────────────────────────────────────

async def btn_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("<b>✅ Tâches</b>", reply_markup=TASKS_KEYBOARD)
    return WAITING_TASKS_MENU


async def receive_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_TASK:
        await update.message.reply_text("Description de la tâche ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_TASK

    if raw == BTN_TODAY:
        tasks = get_pending_tasks()
        if not tasks:
            await update.message.reply_text("✨ Aucune tâche en cours !", reply_markup=TASKS_KEYBOARD)
        else:
            await update.message.reply_text(_format_tasks_report(tasks, "📋 Mes tâches"), reply_markup=TASKS_KEYBOARD)
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
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Sous-menu Gestion ────────────────────────────────────────────────────────

async def btn_gestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    await update.message.reply_text("<b>⚙️ Gestion</b>", reply_markup=GESTION_KEYBOARD)
    return WAITING_GESTION_MENU


async def receive_gestion_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_ACCOUNTS:
        await update.message.reply_text("<b>🏦 Comptes</b>", reply_markup=ACCOUNTS_KEYBOARD)
        return WAITING_ACCOUNTS_MENU

    if raw == BTN_PROJECTS:
        await update.message.reply_text("<b>🗂 Projets</b>", reply_markup=PROJECTS_KEYBOARD)
        return WAITING_PROJECTS_MENU

    if raw == BTN_NEW_CHARGE:
        await update.message.reply_text("Nom de la charge ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_CHARGE_NAME

    if raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Résumé ───────────────────────────────────────────────────────────────────

async def btn_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END
    from datetime import date as _date
    today = _date.today()
    s = get_monthly_summary(today.year, today.month)
    lines = _build_summary_lines(s, today.month, today.year)
    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)
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
        await update.message.reply_text("Saisis la date (ex : 02/06/2026 ou 02/06)", reply_markup=MAIN_KEYBOARD)
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
    msg = movement_confirmation("expense", amount, category=category, account=account_name, d=d)
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
        await update.message.reply_text("Saisis la date (ex : 02/06/2026 ou 02/06)", reply_markup=MAIN_KEYBOARD)
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
    msg = movement_confirmation("income", amount, category=category, account=account_name, project=project_name, d=d)
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Terminer tâche ───────────────────────────────────────────────────────────

async def receive_done_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    try:
        task_id = int(raw.split(".")[0])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Sélection invalide.")
        return WAITING_DONE_SELECT
    if mark_done(task_id):
        await update.message.reply_text("✅ Tâche terminée.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("❌ Tâche introuvable ou déjà terminée.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Nouvelle tâche ───────────────────────────────────────────────────────────

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
        await update.message.reply_text("Saisis la date (ex : 02/06/2026 ou 02/06)", reply_markup=MAIN_KEYBOARD)
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
    msg = task_confirmation(description, project_raw, due_date)
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Charges ──────────────────────────────────────────────────────────────────

async def receive_charge_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    context.user_data["charge_name"] = raw
    await update.message.reply_text("Montant ?", reply_markup=MAIN_KEYBOARD)
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
    msg = f"✅ Charge ajoutée · <b>{esc(name)}</b> — {money(amount)} / {freq}"
    if account_name:
        msg += f" · {esc(account_name)}"
    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Comptes ──────────────────────────────────────────────────────────────────

async def receive_accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_ACCOUNT:
        await update.message.reply_text("Nom du compte ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_ACCOUNT_NAME

    if raw == BTN_ACCOUNTS_BALANCE:
        accounts = get_accounts()
        await update.message.reply_text("<b>🏦 Soldes</b>\n\n" + accounts_block(accounts), reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    if raw == BTN_BACK:
        await update.message.reply_text("<b>⚙️ Gestion</b>", reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    await update.message.reply_text("<b>⚙️ Gestion</b>", reply_markup=GESTION_KEYBOARD)
    return WAITING_GESTION_MENU


async def receive_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    context.user_data["account_name"] = raw
    await update.message.reply_text("Solde initial (0 si vide) ?", reply_markup=MAIN_KEYBOARD)
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
    await update.message.reply_text(f"✅ Compte créé · <b>{esc(name)}</b> — {money(balance)}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Projets ──────────────────────────────────────────────────────────────────

async def receive_projects_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    if raw == BTN_NEW_PROJECT:
        await update.message.reply_text("Nom du projet ?", reply_markup=MAIN_KEYBOARD)
        return WAITING_PROJECT_NAME

    if raw == BTN_PROJECTS_LIST:
        projects = get_projects()
        if not projects:
            await update.message.reply_text("<b>🗂 Projets</b>\n\nAucun projet.", reply_markup=GESTION_KEYBOARD)
        else:
            lines = []
            for p in projects:
                s = get_project_summary(p["name"])
                lines.append(f"• <b>{esc(p['name'])}</b> — {money(s['total'])} ({s['count']} revenus)")
            await update.message.reply_text("<b>🗂 Projets</b>\n\n" + "\n".join(lines), reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    if raw == BTN_BACK:
        await update.message.reply_text("<b>⚙️ Gestion</b>", reply_markup=GESTION_KEYBOARD)
        return WAITING_GESTION_MENU

    await update.message.reply_text("<b>⚙️ Gestion</b>", reply_markup=GESTION_KEYBOARD)
    return WAITING_GESTION_MENU


async def receive_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == BTN_SKIP or raw == BTN_BACK:
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
    insert_project(raw.upper())
    await update.message.reply_text(f"✅ Projet créé · <b>{esc(raw.upper())}</b>", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Construction du handler ──────────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    import re
    btn_filter = filters.TEXT & ~filters.COMMAND
    nav = [
        MessageHandler(filters.Regex(f"^{re.escape(BTN_FINANCE)}$"), btn_finance),
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TASKS)}$"), btn_tasks),
        MessageHandler(filters.Regex(f"^{re.escape(BTN_GESTION)}$"), btn_gestion),
        MessageHandler(filters.Regex(f"^{re.escape(BTN_SUMMARY)}$"), btn_summary),
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
        },
        fallbacks=[],
        per_user=True,
        per_chat=True,
    )
