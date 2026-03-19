"""Главное меню бота."""

from __future__ import annotations
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database import upsert_user, get_month_balance
from keyboards import main_menu_kb, more_menu_kb
from utils import fmt_amount, fmt_signed


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)

    balance = await get_month_balance(user.id)
    income  = balance["income"]
    expense = balance["expense"]
    net     = income - expense

    now     = datetime.now()
    net_str = fmt_signed(net)

    text = (
        f"<i>{now.day:02d}.{now.month:02d}.{now.year}</i>\n\n"
        f"🪙 <b>Баланс: {net_str}</b>\n"
        f"· Расходы: {fmt_amount(expense)} · Доходы: {fmt_amount(income)}"
    )

    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
        except Exception:
            await query.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")


async def show_more_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=more_menu_kb())