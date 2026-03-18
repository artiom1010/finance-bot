"""Главное меню бота."""

from __future__ import annotations
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database import upsert_user, get_month_balance
from keyboards import main_menu_kb
from utils import fmt_amount, fmt_signed, MONTHS_GEN


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)

    balance = await get_month_balance(user.id)
    income  = balance["income"]
    expense = balance["expense"]
    net     = income - expense

    now = datetime.now()
    month = MONTHS_GEN[now.month]

    net_str = fmt_signed(net)
    net_icon = "📈" if net >= 0 else "📉"

    text = (
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"📊 <b>Баланс за {month} {now.year}:</b>\n"
        f"├ 📈 Доходы:   <code>{fmt_amount(income)}</code>\n"
        f"├ 📉 Расходы:  <code>{fmt_amount(expense)}</code>\n"
        f"└ {net_icon} Итого:    <code>{net_str}</code>"
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