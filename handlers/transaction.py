"""
Сценарий создания транзакции (ConversationHandler).

Шаги
----
1. new_transaction  — выбор типа (Расход / Доход)
2. type_chosen      — выбор категории
3. category_chosen  — ввод суммы (текстовое сообщение)
4. amount_received  — запрос заметки (или пропуск)
5. note_received /
   skip_note        — сохранение + подтверждение
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    get_categories,
    get_category_by_id,
    add_transaction,
    get_transaction_details,
    get_category_limit,
    get_month_spent_by_category,
)
from keyboards import type_kb, categories_kb, cancel_kb, back_to_menu_kb, skip_note_kb
from utils import fmt_amount, fmt_date, parse_amount, progress_bar
from handlers.start import show_main_menu

# Состояния ConversationHandler
CHOOSING_TYPE, CHOOSING_CATEGORY, ENTERING_AMOUNT, ENTERING_NOTE = range(4)

TYPE_LABEL = {"expense": "📉 Расход", "income": "📈 Доход"}


# ---------------------------------------------------------------------------
# Шаг 1: выбор типа
# ---------------------------------------------------------------------------

async def new_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 <b>Новая транзакция</b>\n\nВыберите тип:",
        reply_markup=type_kb(),
        parse_mode="HTML",
    )
    return CHOOSING_TYPE


# ---------------------------------------------------------------------------
# Шаг 2: выбор категории
# ---------------------------------------------------------------------------

async def type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    tx_type = query.data.split("_", 1)[1]  # "expense" или "income"
    context.user_data["tx_type"] = tx_type

    categories = await get_categories(update.effective_user.id, tx_type)
    label = TYPE_LABEL[tx_type]

    await query.edit_message_text(
        f"📝 <b>Новая транзакция</b>\n{label}\n\nВыберите категорию:",
        reply_markup=categories_kb(categories),
        parse_mode="HTML",
    )
    return CHOOSING_CATEGORY


async def back_to_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат к выбору типа из экрана категорий."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 <b>Новая транзакция</b>\n\nВыберите тип:",
        reply_markup=type_kb(),
        parse_mode="HTML",
    )
    return CHOOSING_TYPE


# ---------------------------------------------------------------------------
# Шаг 3: ввод суммы
# ---------------------------------------------------------------------------

async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split("_", 1)[1])
    context.user_data["cat_id"] = cat_id

    cat = await get_category_by_id(cat_id)
    cat_label = f"{cat['emoji']} {cat['name']}" if cat else "—"
    context.user_data["cat_label"] = cat_label

    tx_type = context.user_data.get("tx_type", "expense")
    label = TYPE_LABEL[tx_type]

    msg = await query.edit_message_text(
        f"📝 <b>Новая транзакция</b>\n"
        f"{label}  ·  {cat_label}\n\n"
        f"💰 Введите сумму <b>(в L)</b>:\n"
        f"<i>Например: 150 или 1 500.50</i>",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )
    # Сохраняем message_id, чтобы потом его отредактировать
    context.user_data["prompt_msg_id"] = msg.message_id
    context.user_data["chat_id"] = query.message.chat_id

    return ENTERING_AMOUNT


# ---------------------------------------------------------------------------
# Шаг 4: обработка суммы → запрос заметки
# ---------------------------------------------------------------------------

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text
    amount = parse_amount(raw)

    if amount is None:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число, например: <code>150</code> или <code>1500.50</code>",
            parse_mode="HTML",
        )
        return ENTERING_AMOUNT

    context.user_data["amount"] = amount

    # Удаляем сообщение пользователя с суммой
    try:
        await update.message.delete()
    except Exception:
        pass

    tx_type   = context.user_data.get("tx_type", "expense")
    cat_label = context.user_data.get("cat_label", "—")
    label     = TYPE_LABEL[tx_type]
    chat_id   = context.user_data.get("chat_id")
    prompt_id = context.user_data.get("prompt_msg_id")

    note_text = (
        f"📝 <b>Новая транзакция</b>\n"
        f"{label}  ·  {cat_label}\n"
        f"💰 <b>{fmt_amount(amount)}</b>\n\n"
        f"✍️ Добавьте заметку или пропустите:"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=prompt_id,
            text=note_text,
            reply_markup=skip_note_kb(),
            parse_mode="HTML",
        )
    except Exception:
        msg = await update.effective_chat.send_message(
            note_text,
            reply_markup=skip_note_kb(),
            parse_mode="HTML",
        )
        context.user_data["prompt_msg_id"] = msg.message_id
        context.user_data["chat_id"] = msg.chat_id

    return ENTERING_NOTE


# ---------------------------------------------------------------------------
# Шаг 5a: пользователь ввёл заметку
# ---------------------------------------------------------------------------

async def note_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note = update.message.text.strip()[:255]

    try:
        await update.message.delete()
    except Exception:
        pass

    return await _save_transaction(update, context, note=note)


# ---------------------------------------------------------------------------
# Шаг 5b: пользователь нажал «Пропустить»
# ---------------------------------------------------------------------------

async def skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await _save_transaction(update, context, note=None)


# ---------------------------------------------------------------------------
# Общая логика сохранения транзакции
# ---------------------------------------------------------------------------

async def _save_transaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    note: str | None = None,
) -> int:
    """Сохраняет транзакцию и показывает сообщение об успехе."""
    user_id   = update.effective_user.id
    cat_id    = context.user_data["cat_id"]
    amount    = context.user_data["amount"]
    tx_type   = context.user_data.get("tx_type", "expense")
    cat_label = context.user_data.get("cat_label", "—")

    tx_id = await add_transaction(user_id, cat_id, amount, note=note)
    tx    = await get_transaction_details(tx_id)

    label    = TYPE_LABEL[tx_type]
    date_str = fmt_date(tx["created_at"]) if tx else "—"

    success_text = (
        f"✅ <b>Транзакция добавлена!</b>\n\n"
        f"{label}  ·  {cat_label}\n"
        f"💰 <b>{fmt_amount(amount)}</b>\n"
        f"📅 {date_str}"
    )

    if note:
        success_text += f"\n📝 {note}"

    # Проверяем лимит для расходных транзакций
    if tx_type == "expense":
        limit = await get_category_limit(user_id, cat_id)
        if limit is not None:
            spent = await get_month_spent_by_category(user_id, cat_id)
            ratio = spent / limit if limit else 0.0
            if ratio >= 1.0:
                success_text += (
                    f"\n\n🚨 <b>Лимит исчерпан!</b>  "
                    f"{fmt_amount(spent)} / {fmt_amount(limit)}"
                )
            elif ratio >= 0.8:
                pct = round(ratio * 100)
                bar = progress_bar(pct)
                success_text += (
                    f"\n\n⚠️ <b>Использовано {pct}% лимита</b>  "
                    f"{bar}  {fmt_amount(spent)} / {fmt_amount(limit)}"
                )

    chat_id   = context.user_data.get("chat_id")
    prompt_id = context.user_data.get("prompt_msg_id")

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=prompt_id,
            text=success_text,
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await update.effective_chat.send_message(
            success_text,
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )

    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Отмена / fallback
# ---------------------------------------------------------------------------

async def cancel_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_main_menu(update, context)
    return ConversationHandler.END
