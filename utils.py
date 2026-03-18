"""Вспомогательные функции форматирования."""

from __future__ import annotations
from datetime import datetime

MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

MONTHS_NOM = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}

PERIOD_LABELS = {
    "day":   "сегодня",
    "week":  "7 дней",
    "month": "этот месяц",
}


def fmt_amount(amount: float) -> str:
    """150 → '150 L', 1500 → '1 500 L', 150.5 → '150.50 L'"""
    abs_val = abs(amount)
    if abs_val == int(abs_val):
        return f"{int(abs_val):,} L".replace(",", "\u202f")  # narrow no-break space
    return f"{abs_val:,.2f} L".replace(",", "\u202f")


def fmt_signed(amount: float) -> str:
    # sign = "+" if amount > 0 else ""
    sign = "+" if amount > 0 else ("-" if amount < 0 else "")
    return sign + fmt_amount(amount)


def fmt_date(dt_str: str) -> str:
    """'2026-03-17 21:30:00' → '17 марта, 21:30'"""
    try:
        dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        return f"{dt.day} {MONTHS_GEN[dt.month]}, {dt.strftime('%H:%M')}"
    except Exception:
        return dt_str


def parse_amount(text: str) -> float | None:
    """Парсит строку суммы: '150', '1500.50', '1 500,50' → float."""
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
        return round(value, 2) if value > 0 else None
    except ValueError:
        return None


def progress_bar(percent: float, width: int = 10) -> str:
    filled = round(percent / 100 * width)
    return "▓" * filled + "░" * (width - filled)