"""
Админ-панель: /admin — только для авторизованного пользователя.
Просмотр таблиц базы данных прямо в Telegram.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import DB_PATH
import aiosqlite

log = logging.getLogger(__name__)

ADMIN_ID = 7480659195

TABLES = [
    "users",
    "categories",
    "transactions",
    "category_limits",
    "recurring_transactions",
    "user_hidden_categories",
]


def _admin_kb() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(t, callback_data=f"admin_table_{t}")] for t in TABLES]
    return InlineKeyboardMarkup(buttons)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    await update.message.reply_text(
        "🛠 <b>Admin панель</b>\n\nВыберите таблицу:",
        reply_markup=_admin_kb(),
        parse_mode="HTML",
    )


async def admin_show_table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return

    table = query.data.removeprefix("admin_table_")
    if table not in TABLES:
        await query.edit_message_text("❌ Неизвестная таблица.")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(f"SELECT * FROM {table} LIMIT 50")  # noqa: S608
            rows = await cursor.fetchall()
            cursor2 = await db.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in await cursor2.fetchall()]
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")
        return

    if not rows:
        text = f"🗃 <b>{table}</b>\n\n<i>Таблица пуста.</i>"
    else:
        lines = [f"🗃 <b>{table}</b>  <i>({len(rows)} строк)</i>\n"]
        for row in rows:
            parts = []
            for col in cols:
                val = row[col]
                if val is not None:
                    parts.append(f"<b>{col}</b>: {val}")
            lines.append("• " + "  |  ".join(parts))
        text = "\n".join(lines)

    # Telegram лимит — 4096 символов
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (обрезано)</i>"

    await query.edit_message_text(
        text,
        reply_markup=_admin_kb(),
        parse_mode="HTML",
    )
