import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from app.core.config import TELEGRAM_ALLOWED_USER_ID
from app.bot.conversation import MAIN_KEYBOARD, BTN_FINANCE, BTN_TASKS, BTN_GESTION, BTN_SUMMARY, BTN_HISTORY
from app.core.expenses import insert_expense
from app.core.incomes import insert_income
from app.core.tasks import insert_task, get_pending_tasks, mark_done
from app.core.accounts import get_accounts
from app.core.interpreter import interpret


_NAVIGATION_BUTTONS = {BTN_FINANCE, BTN_TASKS, BTN_GESTION, BTN_SUMMARY, BTN_HISTORY}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return
    await update.message.reply_text(
        "🏠 MENU PRINCIPAL\n\nBot opérationnel ✓",
        reply_markup=MAIN_KEYBOARD,
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
        return

    text = update.message.text.strip()

    if text in _NAVIGATION_BUTTONS:
        return

    try:
        intent = await asyncio.to_thread(interpret, text)
    except Exception:
        await update.message.reply_text("Je n'ai pas compris.", reply_markup=MAIN_KEYBOARD)
        return

    kind = intent.get("type")

    if kind == "expense":
        amount = float(intent["amount"])
        description = intent["description"]
        category = intent.get("category") or None
        account_name = intent.get("account") or None
        result = insert_expense(amount, description, category, account_name)
        msg = f"✅ Dépense : {amount:.2f} € — {description}"
        if result is False:
            msg += f"\n⚠️ Compte '{account_name}' introuvable."
        await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)

    elif kind == "income":
        amount = float(intent["amount"])
        description = intent["description"]
        category = intent.get("category") or None
        account_name = intent.get("account") or None
        project_name = intent.get("project") or None
        result = insert_income(amount, description, category, account_name, None, project_name)
        msg = f"✅ Revenu : {amount:.2f} € — {description}"
        if result is False:
            msg += f"\n⚠️ Compte '{account_name}' introuvable."
        await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)

    elif kind == "task":
        description = intent["description"]
        insert_task(description)
        await update.message.reply_text(f"✅ Tâche ajoutée : {description}", reply_markup=MAIN_KEYBOARD)

    elif kind == "tasks_list":
        tasks = get_pending_tasks()
        if not tasks:
            await update.message.reply_text("✨ Aucune tâche en cours.", reply_markup=MAIN_KEYBOARD)
        else:
            from app.bot.conversation import _format_tasks_report
            await update.message.reply_text(_format_tasks_report(tasks, "📋 MES TÂCHES"), reply_markup=MAIN_KEYBOARD)

    elif kind == "task_done":
        task_id = int(intent["id"])
        if mark_done(task_id):
            await update.message.reply_text(f"✅ Tâche {task_id} terminée.", reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text(f"❌ Tâche {task_id} introuvable.", reply_markup=MAIN_KEYBOARD)

    elif kind == "cash":
        accounts = get_accounts()
        if not accounts:
            await update.message.reply_text("Aucun compte trouvé.", reply_markup=MAIN_KEYBOARD)
        else:
            lines = [f"  {a['name']} : {float(a['balance']):.2f} €" for a in accounts]
            await update.message.reply_text("💳 Soldes\n\n" + "\n".join(lines), reply_markup=MAIN_KEYBOARD)

    else:
        await update.message.reply_text("Je n'ai pas compris.", reply_markup=MAIN_KEYBOARD)
