"""
Управление регулярными транзакциями.

Сценарии
--------
• Просмотр списка регулярных транзакций
• Добавление нового шаблона (ConversationHandler)
• Удаление шаблона
• Подтверждение транзакции по уведомлению
• Ежедневная задача рассылки уведомлений (JobQueue)
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    get_categories,
    add_transaction,
    add_recurring,
    get_recurring_list,
    get_recurring_by_id,
    delete_recurring,
    get_recurring_for_day,
)
from keyboards import (
    recurring_kb,
    rec_type_kb,
    rec_cats_kb,
    recurring_confirm_kb,
    back_to_menu_kb,
    cancel_kb,
)
from utils import fmt_amount, parse_amount

# Состояния ConversationHandler
REC_TYPE, REC_CAT, REC_AMOUNT, REC_DAY = range(4)

TYPE_LABEL = {"expense": "📉 Расход", "income": "📈 Доход"}


# ---------------------------------------------------------------------------
# Показ списка регулярных транзакций
# ---------------------------------------------------------------------------

async def show_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список регулярных транзакций. callback: 'recurring'."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    items = await get_recurring_list(user_id)

    if items:
        lines = ["🔄 <b>Регулярные транзакции</b>\n"]
        for item in items:
            lines.append(
                f"• {item['cat_emoji']} <b>{item['label']}</b>  "
                f"{fmt_amount(item['amount'])}  "
                f"(каждое {item['day_of_month']} число)"
            )
        text = "\n".join(lines)
    else:
        text = "🔄 <b>Регулярные транзакции</b>\n\n<i>Нет регулярных транзакций.</i>"

    await query.edit_message_text(
        text,
        reply_markup=recurring_kb(items),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# ConversationHandler: добавление регулярной транзакции
# ---------------------------------------------------------------------------

async def start_add_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Точка входа: выбор типа. callback: 'add_recurring'."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🔄 <b>Новая регулярная транзакция</b>\n\nВыберите тип:",
        reply_markup=rec_type_kb(),
        parse_mode="HTML",
    )
    return REC_TYPE


async def rec_type_chosen(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Пользователь выбрал тип. callback: rec_type_(expense|income)."""
    query = update.callback_query
    await query.answer()

    tx_type = query.data.split("_")[2]  # rec_type_expense → expense
    context.user_data["rec_type"] = tx_type

    user_id = update.effective_user.id
    categories = await get_categories(user_id, type_=tx_type)
    label = TYPE_LABEL[tx_type]

    await query.edit_message_text(
        f"🔄 <b>Новая регулярная транзакция</b>\n{label}\n\nВыберите категорию:",
        reply_markup=rec_cats_kb(categories),
        parse_mode="HTML",
    )
    return REC_CAT


async def rec_cat_chosen(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Пользователь выбрал категорию. callback: rec_cat_{id}."""
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split("_")[2])  # rec_cat_{id}
    context.user_data["rec_cat_id"] = cat_id

    from database import get_category_by_id
    cat = await get_category_by_id(cat_id)
    cat_label = f"{cat['emoji']} {cat['name']}" if cat else "—"
    context.user_data["rec_cat_label"] = cat_label

    tx_type = context.user_data.get("rec_type", "expense")
    label = TYPE_LABEL[tx_type]

    msg = await query.edit_message_text(
        f"🔄 <b>Новая регулярная транзакция</b>\n"
        f"{label}  ·  {cat_label}\n\n"
        f"💰 Введите сумму <b>(в L)</b>:",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )
    context.user_data["rec_prompt_msg_id"] = msg.message_id
    context.user_data["rec_chat_id"] = query.message.chat_id
    return REC_AMOUNT


async def rec_amount_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Пользователь ввёл сумму — запрашиваем день месяца."""
    raw = update.message.text
    amount = parse_amount(raw)

    if amount is None:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число, например: <code>1500</code>",
            parse_mode="HTML",
        )
        return REC_AMOUNT

    context.user_data["rec_amount"] = amount

    try:
        await update.message.delete()
    except Exception:
        pass

    cat_label = context.user_data.get("rec_cat_label", "—")
    tx_type   = context.user_data.get("rec_type", "expense")
    label     = TYPE_LABEL[tx_type]
    chat_id   = context.user_data.get("rec_chat_id")
    prompt_id = context.user_data.get("rec_prompt_msg_id")

    day_text = (
        f"🔄 <b>Новая регулярная транзакция</b>\n"
        f"{label}  ·  {cat_label}\n"
        f"💰 <b>{fmt_amount(amount)}</b>\n\n"
        f"📅 Введите день месяца <b>(1–31)</b>:"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=prompt_id,
            text=day_text,
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )
    except Exception:
        msg = await update.effective_chat.send_message(
            day_text, reply_markup=cancel_kb(), parse_mode="HTML"
        )
        context.user_data["rec_prompt_msg_id"] = msg.message_id
        context.user_data["rec_chat_id"] = msg.chat_id

    return REC_DAY


async def rec_day_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Пользователь ввёл день месяца — сохраняем шаблон."""
    raw = update.message.text.strip()

    try:
        day = int(raw)
        if not (1 <= day <= 31):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число от 1 до 31.",
            parse_mode="HTML",
        )
        return REC_DAY

    user_id   = update.effective_user.id
    cat_id    = context.user_data["rec_cat_id"]
    cat_label = context.user_data.get("rec_cat_label", "—")
    amount    = context.user_data["rec_amount"]
    tx_type   = context.user_data.get("rec_type", "expense")
    label     = TYPE_LABEL[tx_type]

    # label для шаблона — название категории
    rec_label = cat_label

    await add_recurring(
        user_id=user_id,
        cat_id=cat_id,
        amount=amount,
        note=None,
        day_of_month=day,
        label=rec_label,
    )

    try:
        await update.message.delete()
    except Exception:
        pass

    success_text = (
        f"✅ <b>Регулярная транзакция добавлена!</b>\n\n"
        f"{label}  ·  {cat_label}\n"
        f"💰 <b>{fmt_amount(amount)}</b>\n"
        f"📅 Каждое <b>{day}</b> число месяца"
    )

    chat_id   = context.user_data.get("rec_chat_id")
    prompt_id = context.user_data.get("rec_prompt_msg_id")

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
# Удаление регулярной транзакции
# ---------------------------------------------------------------------------

async def delete_recurring_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик callback del_rec_{id}."""
    query = update.callback_query
    await query.answer("Удалено 🗑")

    rec_id  = int(query.data.split("_")[2])  # del_rec_{id}
    user_id = update.effective_user.id

    await delete_recurring(user_id, rec_id)

    items = await get_recurring_list(user_id)

    if items:
        lines = ["🔄 <b>Регулярные транзакции</b>\n"]
        for item in items:
            lines.append(
                f"• {item['cat_emoji']} <b>{item['label']}</b>  "
                f"{fmt_amount(item['amount'])}  "
                f"(каждое {item['day_of_month']} число)"
            )
        text = "\n".join(lines)
    else:
        text = "🔄 <b>Регулярные транзакции</b>\n\n<i>Нет регулярных транзакций.</i>"

    await query.edit_message_text(
        text,
        reply_markup=recurring_kb(items),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Подтверждение регулярной транзакции из уведомления
# ---------------------------------------------------------------------------

async def confirm_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик callback confirm_rec_{id} — быстрое добавление транзакции."""
    query = update.callback_query
    await query.answer("✅ Транзакция добавлена!")

    rec_id  = int(query.data.split("_")[2])  # confirm_rec_{id}
    user_id = update.effective_user.id

    rec = await get_recurring_by_id(rec_id)
    if rec is None:
        await query.answer("Шаблон не найден.", show_alert=True)
        return

    await add_transaction(
        user_id=user_id,
        category_id=rec["category_id"],
        amount=rec["amount"],
        note=rec["note"],
    )

    # Обновляем сообщение — помечаем как выполненное
    try:
        original_text = query.message.text or ""
        await query.edit_message_text(
            original_text + f"\n\n✅ <b>{rec['label']}</b> — добавлено!",
            reply_markup=query.message.reply_markup,
            parse_mode="HTML",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ежедневная задача JobQueue
# ---------------------------------------------------------------------------

async def check_recurring_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная задача: рассылает напоминания о регулярных транзакциях."""
    import datetime as dt

    today = dt.date.today()
    day = today.day

    records = await get_recurring_for_day(day)
    if not records:
        return

    # Группируем по user_id
    by_user: dict[int, list] = {}
    for rec in records:
        uid = rec["user_id"]
        by_user.setdefault(uid, []).append(rec)

    for user_id, items in by_user.items():
        text = "🔔 <b>Напоминание о регулярных транзакциях!</b>\n\n"
        for item in items:
            text += (
                f"• {item['cat_emoji']} <b>{item['label']}</b>  "
                f"{fmt_amount(item['amount'])}\n"
            )
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=recurring_confirm_kb(items),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Отмена / fallback
# ---------------------------------------------------------------------------

async def cancel_to_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Возврат к списку регулярных транзакций."""
    context.user_data.clear()
    await show_recurring(update, context)
    return ConversationHandler.END
