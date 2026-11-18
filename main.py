"""One-click launcher for PyCharm, Windows and Raspberry Pi."""
import logging
import platform
import threading

from app.database import init
from app.monitor import main as monitor_main
from app.telegram_bot import main as bot_main


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init()
    print("⚡ Ayla Power Monitor v1.0.1")
    print("Система:", platform.system())
    print("Моніторинг + Telegram-бот запускаються разом")
    monitor_thread = threading.Thread(target=monitor_main, name="power-monitor", daemon=True)
    monitor_thread.start()
    try:
        bot_main()  # Telegram polling must run on the main thread.
    except KeyboardInterrupt:
        print("Зупинено")


if __name__ == "__main__":
    main()
