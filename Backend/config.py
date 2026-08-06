import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

# Database Config
DB_HOST = os.getenv("DB_HOST") or ""
DB_NAME = os.getenv("DB_NAME") or ""
DB_USER = os.getenv("DB_USER") or ""
DB_PASSWORD = os.getenv("DB_PASSWORD") or ""

# Telegram Config
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""
CHAT_ID = os.getenv("CHAT_ID") or ""
GROUP_ID = os.getenv("GROUP_ID") or ""