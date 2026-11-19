"""Single entry point: monitoring on Raspberry Pi + Telegram on all platforms."""
import logging
import platform
import threading

from app.database import init
from app.telegram_bot import main as bot_main


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    init()
    system = platform.system()
    print('⚡ Ayla Power Monitor v1.4.0 |', system)
    if system == 'Linux':
        from app.monitor import main as monitor_main
        threading.Thread(target=monitor_main, name='power-monitor', daemon=True).start()
        print('Моніторинг Raspberry Pi + Telegram запущені через main.py')
    else:
        print('Тестування Telegram без фіктивних heartbeat: реальний моніторинг лише на Linux')
    try:
        bot_main()  # Telegram polling must run on the main thread.
    except KeyboardInterrupt:
        print('Зупинено')


if __name__ == '__main__':
    main()
