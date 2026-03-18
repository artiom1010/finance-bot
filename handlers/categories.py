"""
Управление категориями.

Сценарии
--------
• Просмотр активных категорий (расходы / доходы)
• Скрыть системную категорию  → она пропадёт из списка при добавлении транзакции
• Восстановить скрытую         → появится снова
• Удалить личную категорию
• Добавить свою категорию (ConversationHandler: тип → эмодзи + название)
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    get_categories,
    get_hidden_categories,
    hide_category,
    unhide_category,
    delete_user_category,
    add_user_category,
)
from keyboards import (
    categories_manage_kb,
    cat_list_kb,
    hidden_cats_kb,
    add_cat_type_kb,
    back_to_cats_kb,
    back_to_menu_kb,
)

# Состояния ConversationHandler для добавления категории
ADD_CAT_TYPE, ADD_CAT_TEXT = range(2)

TYPE_LABEL = {"expense": "📉 Расходы", "income": "📈 Доходы"}


# ---------------------------------------------------------------------------
# Главное меню категорий
# ---------------------------------------------------------------------------

async def show_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🗂 <b>Управление категориями</b>\n\n"
        "<i>Нажмите на категорию в списке:\n"
        "🙈 — скрыть системную\n"
        "🗑 — удалить свою\n"
        "👁 — восстановить скрытую</i>",
        reply_markup=categories_manage_kb(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Список категорий (расходы или доходы)
# ---------------------------------------------------------------------------

async def show_cat_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id  = update.effective_user.id
    cat_type = query.data.split("_")[1]          # "cats_expense" → "expense"
    label    = TYPE_LABEL[cat_type]

    categories = await get_categories(user_id, cat_type)

    text = f"🗂 <b>Категории · {label}</b>\n\n"
    if not categories:
        text += "<i>Нет активных категорий.</i>"

    await query.edit_message_text(
        text,
        reply_markup=cat_list_kb(categories, user_id, cat_type),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Скрыть / восстановить / удалить
# ---------------------------------------------------------------------------

async def hide_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Категория скрыта 🙈")

    parts   = query.data.split("_")             # hide_cat_5_expense
    cat_id  = int(parts[2])
    cat_type = parts[3]

    await hide_category(update.effective_user.id, cat_id)

    # Обновляем тот же список
    user_id    = update.effective_user.id
    categories = await get_categories(user_id, cat_type)
    label      = TYPE_LABEL[cat_type]

    await query.edit_message_text(
        f"🗂 <b>Категории · {label}</b>\n\n",
        reply_markup=cat_list_kb(categories, user_id, cat_type),
        parse_mode="HTML",
    )


async def unhide_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Категория восстановлена 👁")

    cat_id = int(query.data.split("_")[2])      # unhide_cat_5
    await unhide_category(update.effective_user.id, cat_id)

    # Обновляем список скрытых
    hidden = await get_hidden_categories(update.effective_user.id)
    await query.edit_message_text(
        "🙈 <b>Скрытые категории</b>\n\n"
        "<i>Нажмите 👁 — чтобы вернуть категорию в список.</i>",
        reply_markup=hidden_cats_kb(hidden),
        parse_mode="HTML",
    )


async def delete_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    parts    = query.data.split("_")            # del_cat_5_expense
    cat_id   = int(parts[2])
    cat_type = parts[3]

    deleted = await delete_user_category(update.effective_user.id, cat_id)
    await query.answer("Удалено 🗑" if deleted else "Не удалось удалить")

    user_id    = update.effective_user.id
    categories = await get_categories(user_id, cat_type)
    label      = TYPE_LABEL[cat_type]

    await query.edit_message_text(
        f"🗂 <b>Категории · {label}</b>\n\n",
        reply_markup=cat_list_kb(categories, user_id, cat_type),
        parse_mode="HTML",
    )


async def show_hidden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    hidden = await get_hidden_categories(update.effective_user.id)
    await query.edit_message_text(
        "🙈 <b>Скрытые категории</b>\n\n"
        "<i>Нажмите 👁 — чтобы вернуть категорию в список.</i>",
        reply_markup=hidden_cats_kb(hidden),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Добавление своей категории (ConversationHandler)
# ---------------------------------------------------------------------------

async def start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ <b>Новая категория</b>\n\nВыберите тип:",
        reply_markup=add_cat_type_kb(),
        parse_mode="HTML",
    )
    return ADD_CAT_TYPE


async def add_cat_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    cat_type = query.data.split("_")[1]         # "newcat_expense" → "expense"
    context.user_data["new_cat_type"] = cat_type
    label = TYPE_LABEL[cat_type]

    msg = await query.edit_message_text(
        f"➕ <b>Новая категория</b> · {label}\n\n"
        "Отправьте <b>эмодзи</b> и <b>название</b> через пробел:\n"
        "<i>Например: 🎯 Спорт</i>",
        reply_markup=back_to_cats_kb(),
        parse_mode="HTML",
    )
    context.user_data["add_prompt_msg_id"] = msg.message_id
    context.user_data["add_chat_id"]       = query.message.chat_id
    return ADD_CAT_TEXT


async def add_cat_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text  = update.message.text.strip()
    parts = text.split(" ", 1)

    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "❌ Формат: <b>эмодзи пробел название</b>\n"
            "Например: <code>🎯 Спорт</code>",
            parse_mode="HTML",
        )
        return ADD_CAT_TEXT

    emoji    = parts[0]
    name     = parts[1].strip()[:30]
    cat_type = context.user_data.get("new_cat_type", "expense")
    user_id  = update.effective_user.id

    try:
        await add_user_category(user_id, name, cat_type, emoji)
    except ValueError:
        await update.message.reply_text(
            f"❌ Категория <b>{name}</b> уже существует. Введите другое название.",
            parse_mode="HTML",
        )
        return ADD_CAT_TEXT

    try:
        await update.message.delete()
    except Exception:
        pass

    label        = TYPE_LABEL[cat_type]
    chat_id      = context.user_data.get("add_chat_id")
    prompt_msg   = context.user_data.get("add_prompt_msg_id")

    success_text = (
        f"✅ <b>Категория добавлена!</b>\n\n"
        f"{emoji}  <b>{name}</b>\n"
        f"{label}"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=prompt_msg,
            text=success_text,
            reply_markup=back_to_cats_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await update.effective_chat.send_message(
            success_text, reply_markup=back_to_cats_kb(), parse_mode="HTML"
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_add_to_cats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_categories_menu(update, context)
    return ConversationHandler.END
