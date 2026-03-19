"""Точка входа. Регистрирует все хэндлеры и запускает polling."""

from __future__ import annotations
import datetime as dt
import logging
import warnings

from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from telegram.error import NetworkError

from config import BOT_TOKEN
from database import init_db
from handlers.admin import admin_command, admin_show_table
from handlers.start import show_main_menu, show_more_menu
from handlers.transaction import (
    new_transaction,
    new_expense,
    new_income,
    type_chosen,
    back_to_type,
    category_chosen,
    amount_received,
    note_received,
    skip_note,
    cancel_to_menu,
    CHOOSING_TYPE,
    CHOOSING_CATEGORY,
    ENTERING_AMOUNT,
    ENTERING_NOTE,
)
from handlers.stats import show_stats_menu, show_stats, show_history, delete_last
from handlers.categories import (
    show_categories_menu,
    show_cat_list,
    hide_cat,
    unhide_cat,
    delete_cat,
    show_hidden,
    start_add_category,
    add_cat_type_chosen,
    add_cat_text_received,
    cancel_add_to_cats,
    ADD_CAT_TYPE,
    ADD_CAT_TEXT,
)
from handlers.limits import (
    show_limits,
    start_add_limit,
    limit_cat_chosen,
    limit_amount_received,
    delete_limit_handler,
    cancel_to_limits,
    LIMIT_CHOOSING_CAT,
    LIMIT_ENTERING_AMOUNT,
)
from handlers.recurring import (
    show_recurring,
    start_add_recurring,
    rec_type_chosen,
    rec_cat_chosen,
    rec_amount_received,
    rec_day_received,
    delete_recurring_handler,
    confirm_recurring,
    check_recurring_job,
    cancel_to_recurring,
    REC_TYPE,
    REC_CAT,
    REC_AMOUNT,
    REC_DAY,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _error_handler(update: object, context) -> None:
    if isinstance(context.error, NetworkError):
        logging.warning("Сетевая ошибка (автоматический повтор): %s", context.error)
        return
    logging.error("Необработанная ошибка:", exc_info=context.error)


async def _post_init(app: Application) -> None:
    await init_db()
    logging.info("БД инициализирована.")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # ── Сценарий создания транзакции ─────────────────────────────────────────
    transaction_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(new_transaction, pattern="^new_transaction$"),
            CallbackQueryHandler(new_expense,     pattern="^new_expense$"),
            CallbackQueryHandler(new_income,      pattern="^new_income$"),
        ],
        states={
            CHOOSING_TYPE: [
                CallbackQueryHandler(type_chosen, pattern=r"^type_(expense|income)$"),
            ],
            CHOOSING_CATEGORY: [
                CallbackQueryHandler(category_chosen, pattern=r"^cat_\d+$"),
                CallbackQueryHandler(back_to_type,    pattern="^back_to_type$"),
            ],
            ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received),
            ],
            ENTERING_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_received),
                CallbackQueryHandler(skip_note, pattern="^skip_note$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_to_menu, pattern="^back_to_menu$"),
            CommandHandler("start",              cancel_to_menu),
        ],
        allow_reentry=True,
    )

    # ── Сценарий добавления категории ────────────────────────────────────────
    add_category_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_category, pattern="^add_category$"),
        ],
        states={
            ADD_CAT_TYPE: [
                CallbackQueryHandler(add_cat_type_chosen, pattern=r"^newcat_(expense|income)$"),
            ],
            ADD_CAT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_cat_text_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add_to_cats, pattern="^categories_menu$"),
            CommandHandler("start",                  cancel_add_to_cats),
        ],
        allow_reentry=True,
    )

    # ── Сценарий добавления лимита ────────────────────────────────────────────
    add_limit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_limit, pattern="^add_limit$"),
        ],
        states={
            LIMIT_CHOOSING_CAT: [
                CallbackQueryHandler(limit_cat_chosen, pattern=r"^limit_cat_\d+$"),
            ],
            LIMIT_ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, limit_amount_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_to_limits, pattern="^limits$"),
            CallbackQueryHandler(cancel_to_menu,   pattern="^back_to_menu$"),
            CommandHandler("start",                cancel_to_menu),
        ],
        allow_reentry=True,
    )

    # ── Сценарий добавления регулярной транзакции ─────────────────────────────
    add_recurring_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_recurring, pattern="^add_recurring$"),
        ],
        states={
            REC_TYPE: [
                CallbackQueryHandler(rec_type_chosen, pattern=r"^rec_type_(expense|income)$"),
            ],
            REC_CAT: [
                CallbackQueryHandler(rec_cat_chosen, pattern=r"^rec_cat_\d+$"),
            ],
            REC_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_amount_received),
            ],
            REC_DAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rec_day_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_to_recurring, pattern="^recurring$"),
            CallbackQueryHandler(cancel_to_menu,      pattern="^back_to_menu$"),
            CommandHandler("start",                   cancel_to_menu),
        ],
        allow_reentry=True,
    )

    # ── Регистрация хэндлеров ────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", show_main_menu))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(admin_show_table, pattern=r"^admin_table_\w+$"))
    app.add_handler(transaction_conv)
    app.add_handler(add_category_conv)
    app.add_handler(add_limit_conv)
    app.add_handler(add_recurring_conv)

    # Статистика
    app.add_handler(CallbackQueryHandler(show_stats_menu, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(show_stats,      pattern=r"^stats_(day|week|month)$"))

    # История + удаление
    app.add_handler(CallbackQueryHandler(show_history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(delete_last,  pattern="^delete_last$"))

    # Категории
    app.add_handler(CallbackQueryHandler(show_categories_menu, pattern="^categories_menu$"))
    app.add_handler(CallbackQueryHandler(show_cat_list,        pattern=r"^cats_(expense|income)$"))
    app.add_handler(CallbackQueryHandler(show_hidden,          pattern="^cats_hidden$"))
    app.add_handler(CallbackQueryHandler(hide_cat,             pattern=r"^hide_cat_\d+_(expense|income)$"))
    app.add_handler(CallbackQueryHandler(unhide_cat,           pattern=r"^unhide_cat_\d+$"))
    app.add_handler(CallbackQueryHandler(delete_cat,           pattern=r"^del_cat_\d+_(expense|income)$"))

    # Лимиты
    app.add_handler(CallbackQueryHandler(show_limits,          pattern="^limits$"))
    app.add_handler(CallbackQueryHandler(delete_limit_handler, pattern=r"^del_limit_\d+$"))

    # Регулярные транзакции
    app.add_handler(CallbackQueryHandler(show_recurring,          pattern="^recurring$"))
    app.add_handler(CallbackQueryHandler(delete_recurring_handler, pattern=r"^del_rec_\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_recurring,        pattern=r"^confirm_rec_\d+$"))

    # Noop
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))

    # Главное меню (back_to_menu вне разговора)
    app.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(show_more_menu, pattern="^more_menu$"))

    app.add_error_handler(_error_handler)

    # ── JobQueue: ежедневные напоминания о регулярных транзакциях ─────────────
    app.job_queue.run_daily(
        check_recurring_job,
        time=dt.time(9, 0, 0, tzinfo=dt.timezone.utc),
    )

    logging.info("Бот запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
