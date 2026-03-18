"""
Управление лимитами расходов по категориям.

Сценарии
--------
• Просмотр лимитов с прогресс-барами
• Добавление / редактирование лимита (ConversationHandler)
• Удаление лимита
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    get_categories,
    get_all_limits_with_spending,
    set_category_limit,
    delete_category_limit,
)
from keyboards import limits_kb, limit_cats_kb, back_to_menu_kb, cancel_kb
from utils import fmt_amount, progress_bar

# Состояния ConversationHandler
LIMIT_CHOOSING_CAT, LIMIT_ENTERING_AMOUNT = range(2)


# ---------------------------------------------------------------------------
# Показ списка лимитов
# ---------------------------------------------------------------------------

async def show_limits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список лимитов с прогресс-барами."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    limits_data = await get_all_limits_with_spending(user_id)

    if limits_data:
        lines = ["💰 <b>Лимиты расходов</b>\n"]
        for item in limits_data:
            spent = item["spent"]
            limit_amount = item["limit_amount"]
            pct = min(spent / limit_amount * 100, 100) if limit_amount else 0
            bar = progress_bar(pct)
            icon = "🚨" if pct >= 100 else ("⚠️" if pct >= 80 else "✅")
            lines.append(
                f"{icon} {item['cat_emoji']} <b>{item['cat_name']}</b>\n"
                f"   {bar} {fmt_amount(spent)} / {fmt_amount(limit_amount)}"
            )
        text = "\n".join(lines)
    else:
        text = "💰 <b>Лимиты расходов</b>\n\n<i>Лимиты не установлены.</i>"

    await query.edit_message_text(
        text,
        reply_markup=limits_kb(limits_data),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# ConversationHandler: добавление/редактирование лимита
# ---------------------------------------------------------------------------

async def start_add_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа: выбор категории для лимита."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    categories = await get_categories(user_id, type_="expense")

    await query.edit_message_text(
        "💰 <b>Новый лимит</b>\n\nВыберите категорию расходов:",
        reply_markup=limit_cats_kb(categories),
        parse_mode="HTML",
    )
    return LIMIT_CHOOSING_CAT


async def limit_cat_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь выбрал категорию — запрашиваем сумму лимита."""
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split("_")[2])  # limit_cat_{id}
    context.user_data["limit_cat_id"] = cat_id

    # Получаем данные категории для отображения
    from database import get_category_by_id
    cat = await get_category_by_id(cat_id)
    cat_label = f"{cat['emoji']} {cat['name']}" if cat else "—"
    context.user_data["limit_cat_label"] = cat_label

    msg = await query.edit_message_text(
        f"💰 <b>Новый лимит</b>  ·  {cat_label}\n\n"
        f"Введите сумму лимита <b>(в L)</b> на месяц:\n"
        f"<i>Например: 5000</i>",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )
    context.user_data["limit_prompt_msg_id"] = msg.message_id
    context.user_data["limit_chat_id"] = query.message.chat_id
    return LIMIT_ENTERING_AMOUNT


async def limit_amount_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Пользователь ввёл сумму лимита — сохраняем."""
    from utils import parse_amount

    raw = update.message.text
    amount = parse_amount(raw)

    if amount is None:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число, например: <code>5000</code>",
            parse_mode="HTML",
        )
        return LIMIT_ENTERING_AMOUNT

    user_id   = update.effective_user.id
    cat_id    = context.user_data["limit_cat_id"]
    cat_label = context.user_data.get("limit_cat_label", "—")

    await set_category_limit(user_id, cat_id, amount)

    try:
        await update.message.delete()
    except Exception:
        pass

    success_text = (
        f"✅ <b>Лимит установлен!</b>\n\n"
        f"{cat_label}\n"
        f"💰 <b>{fmt_amount(amount)}</b> / месяц"
    )

    chat_id   = context.user_data.get("limit_chat_id")
    prompt_id = context.user_data.get("limit_prompt_msg_id")

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
# Удаление лимита
# ---------------------------------------------------------------------------

async def delete_limit_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик callback del_limit_{cat_id}."""
    query = update.callback_query
    await query.answer("Лимит удалён 🗑")

    cat_id = int(query.data.split("_")[2])  # del_limit_{cat_id}
    user_id = update.effective_user.id

    await delete_category_limit(user_id, cat_id)

    # Обновляем список лимитов
    limits_data = await get_all_limits_with_spending(user_id)

    if limits_data:
        lines = ["💰 <b>Лимиты расходов</b>\n"]
        for item in limits_data:
            spent = item["spent"]
            limit_amount = item["limit_amount"]
            pct = min(spent / limit_amount * 100, 100) if limit_amount else 0
            bar = progress_bar(pct)
            icon = "🚨" if pct >= 100 else ("⚠️" if pct >= 80 else "✅")
            lines.append(
                f"{icon} {item['cat_emoji']} <b>{item['cat_name']}</b>\n"
                f"   {bar} {fmt_amount(spent)} / {fmt_amount(limit_amount)}"
            )
        text = "\n".join(lines)
    else:
        text = "💰 <b>Лимиты расходов</b>\n\n<i>Лимиты не установлены.</i>"

    await query.edit_message_text(
        text,
        reply_markup=limits_kb(limits_data),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Отмена / fallback
# ---------------------------------------------------------------------------

async def cancel_to_limits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат к списку лимитов из ConversationHandler."""
    context.user_data.clear()
    await show_limits(update, context)
    return ConversationHandler.END
