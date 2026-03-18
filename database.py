"""Database layer — SQLite с ACID + нормализованная схема (1NF / 2NF).

Таблицы
-------
users                  — Telegram-пользователи (PK = Telegram user_id)
categories             — справочник категорий; user_id=NULL → системная (для всех),
                         user_id=N → личная категория пользователя N
user_hidden_categories — пользователь скрывает системную категорию (junction table)
transactions           — финансовые операции (FK → users, FK → categories)
category_limits        — лимиты расходов по категориям (составной PK user_id+category_id)
recurring_transactions — регулярные транзакции (шаблоны с day_of_month)

ACID:
  • atomicity  — каждый запрос на изменение идёт через BEGIN/COMMIT aiosqlite
  • consistency — CHECK-constraints (amount > 0, type IN (...))
  • isolation   — WAL journal_mode (читатели не блокируют писателей)
  • durability  — WAL + synchronous=NORMAL (fsync на checkpoint)
"""

from __future__ import annotations

import aiosqlite
from typing import Optional
from config import DB_PATH

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, str, str]] = [
    # name                type       emoji
    ("Зарплата",          "income",  "💼"),
    ("Подарок",           "income",  "🎁"),
    ("Инвестиции",        "income",  "📈"),
    ("Другие доходы",     "income",  "💰"),
    ("Продукты",          "expense", "🛒"),
    ("Еда вне дома",      "expense", "🍽"),
    ("Транспорт",         "expense", "🚗"),
    ("Услуги",            "expense", "🔧"),
    ("Подписки",          "expense", "📱"),
    ("Церковь",           "expense", "⛪"),
    ("Одежда",            "expense", "👗"),
    ("Для дома",          "expense", "🏠"),
    ("Уход",              "expense", "💄"),
    ("Цветы",             "expense", "🌸"),
    ("Другие расходы",    "expense", "💸"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect() -> aiosqlite.Connection:
    return aiosqlite.connect(DB_PATH)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

async def init_db() -> None:
    async with _connect() as db:
        # ACID: WAL mode — concurrent reads, one writer, durable checkpoints
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.executescript("""
            -- 1NF: каждая ячейка атомарна, PK у каждой таблицы
            -- 2NF: нет частичных зависимостей от составного ключа

            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
                            DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS categories (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL,
                type    TEXT    NOT NULL CHECK(type IN ('income', 'expense')),
                emoji   TEXT    NOT NULL,
                -- NULL = системная (видна всем), NOT NULL = личная
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(name, user_id)
            );

            -- Junction table: пользователь скрывает системную категорию.
            -- Составной PK — нет транзитивных зависимостей → 2NF соблюдена.
            CREATE TABLE IF NOT EXISTS user_hidden_categories (
                user_id     INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, category_id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                amount      REAL    NOT NULL CHECK(amount > 0),
                note        TEXT,
                created_at  TEXT    NOT NULL
                            DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (user_id)
                    REFERENCES users(id)      ON DELETE CASCADE,
                FOREIGN KEY (category_id)
                    REFERENCES categories(id) ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(created_at);

            -- Лимиты расходов по категориям (составной PK)
            CREATE TABLE IF NOT EXISTS category_limits (
                user_id     INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                amount      REAL    NOT NULL CHECK(amount > 0),
                PRIMARY KEY (user_id, category_id)
            );

            -- Регулярные транзакции
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
                category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                amount       REAL    NOT NULL CHECK(amount > 0),
                note         TEXT,
                day_of_month INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 31),
                label        TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rec_day  ON recurring_transactions(day_of_month);
            CREATE INDEX IF NOT EXISTS idx_rec_user ON recurring_transactions(user_id);
        """)

        # Миграция: добавить user_id в categories, если колонки ещё нет
        try:
            await db.execute(
                "ALTER TABLE categories ADD COLUMN "
                "user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
            )
        except Exception:
            pass  # колонка уже существует

        # Миграция: добавить note в transactions, если колонки ещё нет
        try:
            await db.execute("ALTER TABLE transactions ADD COLUMN note TEXT")
        except Exception:
            pass  # колонка уже существует

        # Заполняем системные категории один раз
        row = await db.execute_fetchall(
            "SELECT COUNT(*) FROM categories WHERE user_id IS NULL"
        )
        if row[0][0] == 0:
            await db.executemany(
                "INSERT OR IGNORE INTO categories (name, type, emoji) VALUES (?, ?, ?)",
                CATEGORIES,
            )

        await db.commit()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def upsert_user(user_id: int, username: Optional[str], first_name: str) -> None:
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """
            INSERT INTO users (id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def get_categories(user_id: int, type_: Optional[str] = None) -> list:
    """Возвращает активные категории пользователя:
    системные (user_id IS NULL), не скрытые + личные (user_id = ?).
    """
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        base = """
            SELECT * FROM categories
            WHERE (user_id IS NULL OR user_id = ?)
              AND id NOT IN (
                  SELECT category_id FROM user_hidden_categories WHERE user_id = ?
              )
        """
        params: list = [user_id, user_id]
        if type_:
            base += " AND type = ?"
            params.append(type_)
        base += " ORDER BY user_id NULLS FIRST, id"
        return await db.execute_fetchall(base, params)


async def get_category_by_id(cat_id: int):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM categories WHERE id = ?", (cat_id,)
        )
        return rows[0] if rows else None


async def add_user_category(
    user_id: int, name: str, type_: str, emoji: str
) -> int:
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        try:
            cursor = await db.execute(
                "INSERT INTO categories (name, type, emoji, user_id) VALUES (?, ?, ?, ?)",
                (name, type_, emoji, user_id),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except Exception:
            raise ValueError("duplicate")


async def delete_user_category(user_id: int, cat_id: int) -> bool:
    """Удаляет только личную категорию пользователя.

    Перед удалением переносит все связанные транзакции и лимиты
    на системную категорию-заглушку («Другие расходы» / «Другие доходы»),
    чтобы не нарушить FOREIGN KEY constraint.
    """
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")

        # Определяем тип удаляемой категории
        cur = await db.execute(
            "SELECT type FROM categories WHERE id = ? AND user_id = ?",
            (cat_id, user_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False  # не принадлежит пользователю

        cat_type = row[0]
        fallback_name = "Другие расходы" if cat_type == "expense" else "Другие доходы"

        # Находим системную категорию-заглушку
        cur2 = await db.execute(
            "SELECT id FROM categories WHERE name = ? AND user_id IS NULL",
            (fallback_name,),
        )
        fallback = await cur2.fetchone()
        fallback_id = fallback[0] if fallback else None

        if fallback_id:
            await db.execute(
                "UPDATE transactions SET category_id = ? WHERE category_id = ?",
                (fallback_id, cat_id),
            )
            await db.execute(
                "DELETE FROM category_limits WHERE category_id = ? AND user_id = ?",
                (cat_id, user_id),
            )

        result = await db.execute(
            "DELETE FROM categories WHERE id = ? AND user_id = ?",
            (cat_id, user_id),
        )
        await db.commit()
        return result.rowcount > 0


async def hide_category(user_id: int, cat_id: int) -> None:
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT OR IGNORE INTO user_hidden_categories (user_id, category_id) VALUES (?, ?)",
            (user_id, cat_id),
        )
        await db.commit()


async def unhide_category(user_id: int, cat_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            "DELETE FROM user_hidden_categories WHERE user_id = ? AND category_id = ?",
            (user_id, cat_id),
        )
        await db.commit()


async def get_hidden_categories(user_id: int) -> list:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        return await db.execute_fetchall(
            """
            SELECT c.* FROM categories c
            JOIN user_hidden_categories h
              ON c.id = h.category_id
            WHERE h.user_id = ?
            ORDER BY c.type DESC, c.id
            """,
            (user_id,),
        )


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

async def add_transaction(
    user_id: int, category_id: int, amount: float, note: Optional[str] = None
) -> int:
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "INSERT INTO transactions (user_id, category_id, amount, note) VALUES (?, ?, ?, ?)",
            (user_id, category_id, amount, note),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_transaction_details(transaction_id: int):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT t.id, t.amount, t.note, t.created_at,
                   c.name  AS cat_name,
                   c.emoji AS cat_emoji,
                   c.type  AS cat_type
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.id = ?
            """,
            (transaction_id,),
        )
        return rows[0] if rows else None


async def delete_last_transaction(user_id: int) -> bool:
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        rows = await db.execute_fetchall(
            "SELECT id FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        if not rows:
            return False
        await db.execute("DELETE FROM transactions WHERE id = ?", (rows[0][0],))
        await db.commit()
        return True


async def get_history(user_id: int, limit: int = 10) -> list:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        return await db.execute_fetchall(
            """
            SELECT t.id, t.amount, t.note, t.created_at,
                   c.name  AS cat_name,
                   c.emoji AS cat_emoji,
                   c.type  AS cat_type
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )


async def get_stats(user_id: int, period: str) -> tuple[list, list]:
    """
    period: 'day' | 'week' | 'month'
    Возвращает (totals_by_type, breakdown_by_category).
    """
    filters = {
        "day":   "date(t.created_at) = date('now', 'localtime')",
        "week":  "t.created_at >= datetime('now', 'localtime', '-7 days')",
        "month": "strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')",
    }
    where = filters[period]

    async with _connect() as db:
        db.row_factory = aiosqlite.Row

        totals = await db.execute_fetchall(
            f"""
            SELECT c.type, COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND {where}
            GROUP BY c.type
            """,
            (user_id,),
        )

        breakdown = await db.execute_fetchall(
            f"""
            SELECT c.name, c.emoji, c.type,
                   COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND {where}
            GROUP BY c.id
            ORDER BY c.type DESC, total DESC
            """,
            (user_id,),
        )

        return totals, breakdown


async def get_month_balance(user_id: int) -> dict[str, float]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT c.type, COALESCE(SUM(t.amount), 0) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')
            GROUP BY c.type
            """,
            (user_id,),
        )
        result: dict[str, float] = {"income": 0.0, "expense": 0.0}
        for row in rows:
            result[row["type"]] = row["total"]
        return result


# ---------------------------------------------------------------------------
# Category limits
# ---------------------------------------------------------------------------

async def set_category_limit(user_id: int, cat_id: int, amount: float) -> None:
    """Upsert лимита расходов для категории."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """
            INSERT INTO category_limits (user_id, category_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, category_id) DO UPDATE SET amount = excluded.amount
            """,
            (user_id, cat_id, amount),
        )
        await db.commit()


async def delete_category_limit(user_id: int, cat_id: int) -> None:
    """Удаляет лимит для категории."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "DELETE FROM category_limits WHERE user_id = ? AND category_id = ?",
            (user_id, cat_id),
        )
        await db.commit()


async def get_category_limit(user_id: int, cat_id: int) -> Optional[float]:
    """Возвращает лимит или None."""
    async with _connect() as db:
        rows = await db.execute_fetchall(
            "SELECT amount FROM category_limits WHERE user_id = ? AND category_id = ?",
            (user_id, cat_id),
        )
        return rows[0][0] if rows else None


async def get_month_spent_by_category(user_id: int, cat_id: int) -> float:
    """Сумма расходов по категории за текущий месяц."""
    async with _connect() as db:
        rows = await db.execute_fetchall(
            """
            SELECT COALESCE(SUM(t.amount), 0)
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.category_id = ?
              AND c.type = 'expense'
              AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')
            """,
            (user_id, cat_id),
        )
        return rows[0][0] if rows else 0.0


async def get_all_limits_with_spending(user_id: int) -> list:
    """Возвращает список лимитов с текущими тратами за месяц."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        return await db.execute_fetchall(
            """
            SELECT
                cl.category_id,
                cl.amount      AS limit_amount,
                c.name         AS cat_name,
                c.emoji        AS cat_emoji,
                COALESCE(SUM(t.amount), 0) AS spent
            FROM category_limits cl
            JOIN categories c ON c.id = cl.category_id
            LEFT JOIN transactions t
                ON t.category_id = cl.category_id
               AND t.user_id = cl.user_id
               AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')
            WHERE cl.user_id = ?
            GROUP BY cl.category_id
            ORDER BY c.name
            """,
            (user_id,),
        )


# ---------------------------------------------------------------------------
# Recurring transactions
# ---------------------------------------------------------------------------

async def add_recurring(
    user_id: int,
    cat_id: int,
    amount: float,
    note: Optional[str],
    day_of_month: int,
    label: str,
) -> int:
    """Добавляет шаблон регулярной транзакции."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            """
            INSERT INTO recurring_transactions
                (user_id, category_id, amount, note, day_of_month, label)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, cat_id, amount, note, day_of_month, label),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_recurring_list(user_id: int) -> list:
    """Список шаблонов пользователя с данными категории."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        return await db.execute_fetchall(
            """
            SELECT r.id, r.amount, r.note, r.day_of_month, r.label,
                   c.name  AS cat_name,
                   c.emoji AS cat_emoji,
                   c.type  AS cat_type
            FROM recurring_transactions r
            JOIN categories c ON c.id = r.category_id
            WHERE r.user_id = ?
            ORDER BY r.day_of_month, r.id
            """,
            (user_id,),
        )


async def get_recurring_by_id(rec_id: int):
    """Возвращает шаблон по id."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT r.*, c.name AS cat_name, c.emoji AS cat_emoji, c.type AS cat_type
            FROM recurring_transactions r
            JOIN categories c ON c.id = r.category_id
            WHERE r.id = ?
            """,
            (rec_id,),
        )
        return rows[0] if rows else None


async def delete_recurring(user_id: int, rec_id: int) -> bool:
    """Удаляет шаблон регулярной транзакции."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        result = await db.execute(
            "DELETE FROM recurring_transactions WHERE id = ? AND user_id = ?",
            (rec_id, user_id),
        )
        await db.commit()
        return result.rowcount > 0


async def get_recurring_for_day(day_of_month: int) -> list:
    """Все шаблоны на указанный день (все пользователи)."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        return await db.execute_fetchall(
            """
            SELECT r.id, r.user_id, r.amount, r.note, r.day_of_month, r.label,
                   c.name  AS cat_name,
                   c.emoji AS cat_emoji,
                   c.type  AS cat_type,
                   u.first_name
            FROM recurring_transactions r
            JOIN categories c ON c.id = r.category_id
            JOIN users u ON u.id = r.user_id
            WHERE r.day_of_month = ?
            ORDER BY r.user_id, r.id
            """,
            (day_of_month,),
        )
