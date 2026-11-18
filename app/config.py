import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE / ".env")
DB_PATH = Path(os.getenv("DB_PATH", str(BASE / "data" / "power_monitor.db")))
INTERVAL = max(5, int(os.getenv("HEARTBEAT_SECONDS", "10")))
TZ = ZoneInfo("Europe/Kyiv")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ADMIN_IDS = {int(v.strip()) for v in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if v.strip().isdigit()}
