# Ayla Power Monitor — v1.3 Telegram Dashboard

Встановлення патча: перенеси вміст ZIP **у корінь існуючого репозиторію**, підтверди заміну файлів. Не видаляй `.env`, `data/`, SQLite та Telegram-сесії. ZIP містить лише змінені файли. Старі `app/web/` та `app/widgets/` залишаються в робочій папці, але більше не використовуються новим ботом.

## Запуск

```powershell
pip install -r requirements.txt
python main.py
```

Або відкрий `main.py` в PyCharm і натисни Run. У `.env` мають бути `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`. На Windows працює тестовий моніторинг; на Pi — Linux агент. Єдина точка входу — `main.py`.

## Telegram

`/start`, `/dashboard`, `/today` — картка за сьогодні з графіком, кнопками; `/week` — останні 7 днів; `/month` або `/heatmap` — календар-heatmap; `/history` — останні розриви; `/status` — heartbeat; `/yesterday`, `/export`, `/settings`, `/notify_on`, `/notify_off`, `/help` — додаткові команди.

Кнопки перемикають вкладки **редагуванням одного повідомлення** (за винятком fallback, якщо Telegram не дозволяє редагування). Дані заново беруться з SQLite при кожному перемиканні чи натисканні «Оновити». **Автооновлення не передбачено:** Telegram Bot API не підтримує нескінченне автоматичне оновлення без надсилання запитів; ручна кнопка не створює спам.

### Обмеження

- Діаграма показує наявність **heartbeat**, а не достовірний стан електромережі. Невідомий час включає перерви через вимкнення Pi, інтернету чи збій агента.
- Telegram `sendWidget` не використовується (поточна помилка `INPUT_MEDIA_WIDGET_NOT_ALLOWED`). Окремого вебсервера й публічного HTTPS немає.
- Для читабельності графіка необхідні шрифти Arial (Windows) або DejaVu Sans (Raspberry Pi OS; за потреби `sudo apt install fonts-dejavu-core`).
- Історія та графік базуються на поточній структурі SQLite; база не мігрується.
