import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DB_PATH: str = os.getenv("DB_PATH", "finance.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле")