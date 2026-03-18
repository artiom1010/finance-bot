"""Все inline-клавиатуры бота."""

from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕  Новая транзакция", callback_data="new_transaction")],
        [
            InlineKeyboardButton("📊  Статистика", callback_data="stats"),
            InlineKeyboardButton("📋  История",    callback_data="history"),
        ],
        [InlineKeyboardButton("🗂  Категории", callback_data="categories_menu")],
        [
            InlineKeyboardButton("🔄  Регулярные", callback_data="recurring"),
            InlineKeyboardButton("💰  Лимиты",     callback_data="limits"),
        ],
    ])


def type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📉  Расход", callback_data="type_expense"),
            InlineKeyboardButton("📈  Доход",  callback_data="type_income"),
        ],
        [InlineKeyboardButton("🔙  Назад", callback_data="back_to_menu")],
    ])


def categories_kb(categories) -> InlineKeyboardMarkup:
    """Сетка 2 в ряд из категорий выбранного типа."""
    rows = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        btn = InlineKeyboardButton(
            f"{cat['emoji']}  {cat['name']}",
            callback_data=f"cat_{cat['id']}",
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙  Назад", callback_data="back_to_type")])
    return InlineKeyboardMarkup(rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌  Отмена", callback_data="back_to_menu")],
    ])


def skip_note_kb() -> InlineKeyboardMarkup:
    """Клавиатура для шага добавления заметки к транзакции."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏩  Пропустить", callback_data="skip_note"),
            InlineKeyboardButton("❌  Отмена",     callback_data="back_to_menu"),
        ],
    ])


def stats_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅  Сегодня", callback_data="stats_day"),
            InlineKeyboardButton("📆  Неделя",  callback_data="stats_week"),
            InlineKeyboardButton("🗓  Месяц",   callback_data="stats_month"),
        ],
        [InlineKeyboardButton("🔙  Назад", callback_data="back_to_menu")],
    ])


def history_kb(has_transactions: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_transactions:
        rows.append([
            InlineKeyboardButton("🗑  Удалить последнюю", callback_data="delete_last"),
        ])
    rows.append([InlineKeyboardButton("🔙  Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙  В главное меню", callback_data="back_to_menu")],
    ])


# ── Управление категориями ────────────────────────────────────────────────────

def categories_manage_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📉  Расходы", callback_data="cats_expense"),
            InlineKeyboardButton("📈  Доходы",  callback_data="cats_income"),
        ],
        [InlineKeyboardButton("🙈  Скрытые категории", callback_data="cats_hidden")],
        [InlineKeyboardButton("🔙  Назад",              callback_data="back_to_menu")],
    ])


def cat_list_kb(categories, user_id: int, cat_type: str) -> InlineKeyboardMarkup:
    """Список категорий. Системные → [🙈 скрыть], личные → [🗑 удалить]."""
    rows = []
    for cat in categories:
        is_own = cat["user_id"] == user_id
        if is_own:
            cb   = f"del_cat_{cat['id']}_{cat_type}"
            icon = "🗑"
        else:
            cb   = f"hide_cat_{cat['id']}_{cat_type}"
            icon = "🙈"
        rows.append([InlineKeyboardButton(
            f"{cat['emoji']}  {cat['name']}  {icon}",
            callback_data=cb,
        )])
    rows.append([InlineKeyboardButton("➕  Добавить свою", callback_data="add_category")])
    rows.append([InlineKeyboardButton("🔙  Назад",         callback_data="categories_menu")])
    return InlineKeyboardMarkup(rows)


def hidden_cats_kb(categories) -> InlineKeyboardMarkup:
    """Список скрытых категорий. Нажать — вернуть обратно."""
    rows = []
    for cat in categories:
        rows.append([InlineKeyboardButton(
            f"{cat['emoji']}  {cat['name']}  👁",
            callback_data=f"unhide_cat_{cat['id']}",
        )])
    if not rows:
        rows.append([InlineKeyboardButton("—  Список пуст  —", callback_data="noop")])
    rows.append([InlineKeyboardButton("🔙  Назад", callback_data="categories_menu")])
    return InlineKeyboardMarkup(rows)


def add_cat_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📉  Расход", callback_data="newcat_expense"),
            InlineKeyboardButton("📈  Доход",  callback_data="newcat_income"),
        ],
        [InlineKeyboardButton("❌  Отмена", callback_data="categories_menu")],
    ])


def back_to_cats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙  К категориям", callback_data="categories_menu")],
    ])


# ── Лимиты ───────────────────────────────────────────────────────────────────

def limits_kb(limits_data: list) -> InlineKeyboardMarkup:
    """Список лимитов: [категория + прогресс] [🗑] + ➕ + 🔙."""
    from utils import fmt_amount, progress_bar
    rows = []
    for item in limits_data:
        spent = item["spent"]
        limit_amount = item["limit_amount"]
        pct = min(spent / limit_amount * 100, 100) if limit_amount else 0
        bar = progress_bar(pct, width=8)
        label = (
            f"{item['cat_emoji']} {item['cat_name']}  "
            f"{bar}  {fmt_amount(spent)}/{fmt_amount(limit_amount)}"
        )
        rows.append([
            InlineKeyboardButton(label, callback_data="noop"),
            InlineKeyboardButton("🗑", callback_data=f"del_limit_{item['category_id']}"),
        ])
    rows.append([InlineKeyboardButton("➕  Добавить лимит", callback_data="add_limit")])
    rows.append([InlineKeyboardButton("🔙  Назад",          callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def limit_cats_kb(categories: list) -> InlineKeyboardMarkup:
    """Сетка 2-per-row для выбора категории при создании лимита + ❌."""
    rows = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        btn = InlineKeyboardButton(
            f"{cat['emoji']}  {cat['name']}",
            callback_data=f"limit_cat_{cat['id']}",
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌  Отмена", callback_data="limits")])
    return InlineKeyboardMarkup(rows)


# ── Регулярные транзакции ─────────────────────────────────────────────────────

def recurring_kb(items: list) -> InlineKeyboardMarkup:
    """Список регулярных транзакций: [🗑 label] rows + ➕ + 🔙."""
    from utils import fmt_amount
    rows = []
    for item in items:
        label = f"🗑  {item['label']}  ({item['cat_emoji']} {fmt_amount(item['amount'])})"
        rows.append([InlineKeyboardButton(
            label, callback_data=f"del_rec_{item['id']}"
        )])
    rows.append([InlineKeyboardButton("➕  Добавить", callback_data="add_recurring")])
    rows.append([InlineKeyboardButton("🔙  Назад",   callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def rec_type_kb() -> InlineKeyboardMarkup:
    """Выбор типа для регулярной транзакции."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📉  Расход", callback_data="rec_type_expense"),
            InlineKeyboardButton("📈  Доход",  callback_data="rec_type_income"),
        ],
        [InlineKeyboardButton("❌  Отмена", callback_data="recurring")],
    ])


def rec_cats_kb(categories: list) -> InlineKeyboardMarkup:
    """Сетка 2-per-row для выбора категории регулярной транзакции + 🔙."""
    rows = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        btn = InlineKeyboardButton(
            f"{cat['emoji']}  {cat['name']}",
            callback_data=f"rec_cat_{cat['id']}",
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙  Назад", callback_data="recurring")])
    return InlineKeyboardMarkup(rows)


def recurring_confirm_kb(items: list) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления о регулярных транзакциях."""
    from utils import fmt_amount
    rows = []
    for item in items:
        label = f"✅  {item['cat_emoji']} {item['label']} — {fmt_amount(item['amount'])}"
        rows.append([InlineKeyboardButton(
            label, callback_data=f"confirm_rec_{item['id']}"
        )])
    rows.append([InlineKeyboardButton("⏩  Пропустить всё", callback_data="noop")])
    return InlineKeyboardMarkup(rows)
