from telegram import Update
from telegram.ext import ContextTypes
from app.core.config import TELEGRAM_ALLOWED_USER_ID
from app.bot.conversation import MAIN_KEYBOARD
from app.core.expenses import insert_expense
from app.core.incomes import insert_income
from app.core.tasks import insert_task, get_pending_tasks, mark_done
from app.core.accounts import get_accounts
from app.core.interpreter import interpret
from app.core.utils import parse_account_tag, parse_category_tag, parse_date, parse_project_tag
from app.core.reporting import get_monthly_summary


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return
    await update.message.reply_text("Bot opérationnel.", reply_markup=MAIN_KEYBOARD)


async def dep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Usage : /dep <montant> <description>")
        return

    try:
        amount = float(args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Montant invalide.")
        return

    if amount <= 0:
        await update.message.reply_text("Le montant doit être positif.")
        return

    raw_text = " ".join(args[1:])
    try:
        text, category = parse_category_tag(raw_text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    text, account_name = parse_account_tag(text)
    tokens = text.split()
    date_val = parse_date(tokens[-1]) if tokens else None
    if date_val:
        description = " ".join(tokens[:-1])
    else:
        description = text
    result = insert_expense(amount, description, category, account_name, date_val)
    msg = f"Dépense enregistrée : {amount:.2f} € — {description}"
    if result is False:
        msg += f"\n⚠️ Compte '{account_name}' introuvable, solde non mis à jour."
    await update.message.reply_text(msg)


async def rev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Usage : /rev <montant> <description>")
        return

    try:
        amount = float(args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Montant invalide.")
        return

    if amount <= 0:
        await update.message.reply_text("Le montant doit être positif.")
        return

    raw_text = " ".join(args[1:])
    try:
        text, category = parse_category_tag(raw_text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    text, account_name = parse_account_tag(text)
    text, project_name = parse_project_tag(text)
    tokens = text.split()
    date_val = parse_date(tokens[-1]) if tokens else None
    if date_val:
        description = " ".join(tokens[:-1])
    else:
        description = text
    result = insert_income(amount, description, category, account_name, date_val, project_name)
    msg = f"Revenu enregistré : {amount:.2f} € — {description}"
    if result is False:
        msg += f"\n⚠️ Compte '{account_name}' introuvable, solde non mis à jour."
    await update.message.reply_text(msg)


async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage : /todo <description>")
        return

    description = " ".join(args)
    insert_task(description)
    await update.message.reply_text(f"Tâche ajoutée : {description}")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    tasks = get_pending_tasks()
    if not tasks:
        await update.message.reply_text("Aucune tâche en cours.")
        return

    lines = [f"{t['id']}. {t['description']}" for t in tasks]
    await update.message.reply_text("\n".join(lines))


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage : /done <id>")
        return

    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("ID invalide.")
        return

    if mark_done(task_id):
        await update.message.reply_text(f"Tâche {task_id} marquée comme terminée.")
    else:
        await update.message.reply_text(f"Tâche {task_id} introuvable ou déjà terminée.")


async def cash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    accounts = get_accounts()
    if not accounts:
        await update.message.reply_text("Aucun compte trouvé.")
        return

    lines = [f"{a['name']} : {a['balance']:.2f} €" for a in accounts]
    await update.message.reply_text("\n".join(lines))


async def mois(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    from datetime import date as _date
    today = _date.today()

    args = context.args
    if args:
        try:
            parts = args[0].split("/")
            month, year = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            await update.message.reply_text("Usage : /mois ou /mois MM/YYYY")
            return
    else:
        month, year = today.month, today.year

    s = get_monthly_summary(year, month)
    from app.bot.conversation import _build_summary_lines
    lines = _build_summary_lines(s, month, year)

    await update.message.reply_text("\n".join(lines))


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    text = update.message.text.strip()

    try:
        intent = interpret(text)
    except Exception:
        await update.message.reply_text("Je n'ai pas compris.")
        return

    kind = intent.get("type")

    if kind == "expense":
        amount = float(intent["amount"])
        description = intent["description"]
        category = intent.get("category") or None
        account_name = intent.get("account") or None
        result = insert_expense(amount, description, category, account_name)
        msg = f"Dépense enregistrée : {amount:.2f} € — {description}"
        if result is False:
            msg += f"\n⚠️ Compte '{account_name}' introuvable, solde non mis à jour."
        await update.message.reply_text(msg)

    elif kind == "income":
        amount = float(intent["amount"])
        description = intent["description"]
        category = intent.get("category") or None
        account_name = intent.get("account") or None
        project_name = intent.get("project") or None
        result = insert_income(amount, description, category, account_name, None, project_name)
        msg = f"Revenu enregistré : {amount:.2f} € — {description}"
        if result is False:
            msg += f"\n⚠️ Compte '{account_name}' introuvable, solde non mis à jour."
        await update.message.reply_text(msg)

    elif kind == "task":
        description = intent["description"]
        insert_task(description)
        await update.message.reply_text(f"Tâche ajoutée : {description}")

    elif kind == "tasks_list":
        tasks = get_pending_tasks()
        if not tasks:
            await update.message.reply_text("Aucune tâche en cours.")
        else:
            lines = [f"{t['id']}. {t['description']}" for t in tasks]
            await update.message.reply_text("\n".join(lines))

    elif kind == "task_done":
        task_id = int(intent["id"])
        if mark_done(task_id):
            await update.message.reply_text(f"Tâche {task_id} marquée comme terminée.")
        else:
            await update.message.reply_text(f"Tâche {task_id} introuvable ou déjà terminée.")

    elif kind == "cash":
        accounts = get_accounts()
        if not accounts:
            await update.message.reply_text("Aucun compte trouvé.")
        else:
            lines = [f"{a['name']} : {a['balance']:.2f} €" for a in accounts]
            await update.message.reply_text("\n".join(lines))

    else:
        await update.message.reply_text("Je n'ai pas compris.")
