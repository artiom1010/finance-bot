"""Статистика и история транзакций."""

from __future__ import annotations
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database import get_stats, get_history, delete_last_transaction
from keyboards import stats_period_kb, history_kb, back_to_menu_kb
from utils import fmt_amount, fmt_signed, fmt_date, progress_bar, MONTHS_NOM, PERIOD_LABELS


# ---------------------------------------------------------------------------
# Выбор периода
# ---------------------------------------------------------------------------

async def show_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 <b>Статистика</b>\n\nВыберите период:",
        reply_markup=stats_period_kb(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Отображение статистики
# ---------------------------------------------------------------------------

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    period = query.data.split("_", 1)[1]  # day | week | month
    user_id = update.effective_user.id

    totals_rows, breakdown = await get_stats(user_id, period)

    totals: dict[str, float] = {"income": 0.0, "expense": 0.0}
    for row in totals_rows:
        totals[row["type"]] = row["total"]

    income  = totals["income"]
    expense = totals["expense"]
    net     = income - expense
    net_icon = "📈" if net >= 0 else "📉"

    now = datetime.now()
    if period == "month":
        period_label = f"{MONTHS_NOM[now.month]} {now.year}"
    else:
        period_label = PERIOD_LABELS[period]

    lines = [
        f"📊 <b>Статистика · {period_label}</b>\n",
        f"📈 Доходы:   <code>{fmt_amount(income)}</code>",
        f"📉 Расходы:  <code>{fmt_amount(expense)}</code>",
        f"{net_icon} Баланс:   <code>{fmt_signed(net)}</code>",
    ]

    # Разбивка по категориям
    expense_cats = [r for r in breakdown if r["type"] == "expense"]
    income_cats  = [r for r in breakdown if r["type"] == "income"]

    if expense_cats:
        lines.append("\n<b>─── Расходы ───</b>")
        for row in expense_cats:
            pct = (row["total"] / expense * 100) if expense else 0
            bar = progress_bar(pct, 8)
            lines.append(
                f"{row['emoji']}  {row['name']}\n"
                f"   <code>{bar}</code> <code>{fmt_amount(row['total'])}</code>  <i>{pct:.0f}%</i>"
            )

    if income_cats:
        lines.append("\n<b>─── Доходы ───</b>")
        for row in income_cats:
            pct = (row["total"] / income * 100) if income else 0
            bar = progress_bar(pct, 8)
            lines.append(
                f"{row['emoji']}  {row['name']}\n"
                f"   <code>{bar}</code> <code>{fmt_amount(row['total'])}</code>  <i>{pct:.0f}%</i>"
            )

    if not expense_cats and not income_cats:
        lines.append("\n<i>За этот период транзакций нет.</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# История транзакций
# ---------------------------------------------------------------------------

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    rows = await get_history(user_id, limit=10)

    if not rows:
        await query.edit_message_text(
            "📋 <b>История транзакций</b>\n\n<i>Пока нет ни одной записи.</i>",
            reply_markup=history_kb(False),
            parse_mode="HTML",
        )
        return

    lines = ["📋 <b>Последние транзакции</b>\n"]
    for i, row in enumerate(rows, 1):
        direction = "📉" if row["cat_type"] == "expense" else "📈"
        sign      = "-" if row["cat_type"] == "expense" else "+"
        lines.append(
            f"{i}. {direction} {row['cat_emoji']}  <b>{row['cat_name']}</b>\n"
            f"   <code>{sign}{fmt_amount(row['amount'])}</code>  ·  <i>{fmt_date(row['created_at'])}</i>"
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=history_kb(True),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Удаление последней транзакции
# ---------------------------------------------------------------------------

async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    deleted = await delete_last_transaction(user_id)

    if deleted:
        text = "🗑 <b>Последняя транзакция удалена.</b>"
    else:
        text = "❌ Нет транзакций для удаления."

    await query.edit_message_text(
        text,
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )