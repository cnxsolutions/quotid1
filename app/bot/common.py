"""Briques partagées par tous les parcours : états, réponses, saisie en cours, menu principal."""

from enum import IntEnum
from html import escape
from typing import TypeVar

from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from app.bot import keyboards as kb

FlowT = TypeVar("FlowT")

_FLOW_KEY = "flow"


class State(IntEnum):
    MENU = 0
    PICK = 1
    NAME = 2
    AMOUNT = 3
    FREQUENCY = 4
    KIND = 5
    DUE_MONTH = 6
    DEADLINE = 7
    CONFIRM_DELETE = 8
    TARGET = 9
    POINT_BALANCE = 10
    POINT_INCOME = 11


def text_of(update: Update) -> str:
    message = update.effective_message
    return (message.text or "").strip() if message is not None else ""


def bold(name: str) -> str:
    return f"<b>{escape(name)}</b>"


async def reply(update: Update, text: str, keyboard: ReplyKeyboardMarkup) -> None:
    message = update.effective_message
    if message is not None:
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def peek_flow(context: ContextTypes.DEFAULT_TYPE) -> object | None:
    return context.user_data.get(_FLOW_KEY) if context.user_data is not None else None


def get_flow(context: ContextTypes.DEFAULT_TYPE, flow_type: type[FlowT]) -> FlowT:
    """Saisie en cours, conservée entre deux messages dans user_data."""
    flow = peek_flow(context)
    if not isinstance(flow, flow_type):
        raise RuntimeError(f"Saisie en cours absente ou inattendue : {type(flow).__name__}")
    return flow


def set_flow(context: ContextTypes.DEFAULT_TYPE, flow: object | None) -> None:
    if context.user_data is None:
        return
    if flow is None:
        context.user_data.pop(_FLOW_KEY, None)
    else:
        context.user_data[_FLOW_KEY] = flow


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str | None = None) -> int:
    set_flow(context, None)
    await reply(update, text if text is not None else "🏠 <b>Menu principal</b>", kb.MAIN)
    return ConversationHandler.END
