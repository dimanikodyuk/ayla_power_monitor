# ⚡ Ayla Power Monitor v1.0.0

Автономний облік **роботи Raspberry Pi 4** і розривів моніторингу після зникнення живлення.
Python + SQLite + Telegram. Часовий пояс звітів: `Europe/Kyiv`.

> **Важливо:** RPi без UPS не вимірює мережеву напругу. Періоди без heartbeat — **невідомий стан**, а не доведені відключення. Відновлення електрики передує старту агента; завантаження входить у розрив. Без RTC/NTP час після завантаження може бути некоректним.

## Встановлення на Raspberry Pi OS / Debian

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git
git clone https://github.com/dimanikodyuk/ayla_power_monitor.git
cd ayla_power_monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

Укажіть `TELEGRAM_BOT_TOKEN` (від BotFather), `TELEGRAM_ADMIN_IDS` (числовий Telegram user ID) та `TELEGRAM_CHAT_ID` (числовий ID чату для сповіщень). Для приватного бота ці два ID часто однакові.

**Якщо встановлюєте з ZIP**, розпакуйте файли в `/home/pi/ayla_power_monitor` замість `git clone`. Для іншого користувача або каталогу відредагуйте `User`, `WorkingDirectory` та `ExecStart` в обох service-файлах.

Перший тест у двох терміналах:

```bash
.venv/bin/python -m app.monitor
.venv/bin/python -m app.telegram_bot
```

Зупиніть обидва через Ctrl+C, потім установіть автозапуск:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ayla-power-monitor.service ayla-power-bot.service
systemctl status ayla-power-monitor.service ayla-power-bot.service
journalctl -u ayla-power-monitor -f
```

Перевірте синхронізацію часу: `timedatectl status`. Агент **чекає NTPSynchronized=yes** перед записом часу. Після відключення без інтернету він не створюватиме ненадійних часових міток.

## Telegram-команди

- `/start` — головне меню
- `/help` — довідка
- `/status` — останній heartbeat
- `/today`, `/yesterday`, `/week`, `/month` — статистика
- `/history` — останні розриви
- `/heatmap` — текстова теплова карта (4-годинні блоки)
- `/export` — CSV розривів
- `/settings` — параметри
- `/notify_on`, `/notify_off` — сповіщення про нові розриви

Команди доступні тільки Telegram ID, переліченим у `TELEGRAM_ADMIN_IDS`. `setMyCommands` реєструє меню Telegram.

## Як працює

Монітор кожні `HEARTBEAT_SECONDS` секунд оновлює останній час та Linux boot ID у SQLite. Якщо розрив перевищує 45 секунд або 3 інтервали heartbeat, зберігається запис `unknown`. Після старту Telegram-бот надсилає повідомлення про ще не повідомлені розриви, якщо задано `TELEGRAM_CHAT_ID`.

SQLite використовує WAL і `synchronous=FULL`; **це не гарантує захист SD-картки від фізичного пошкодження**. Регулярно робіть резервні копії SQLite через SQLite backup API або команду `.backup` (не копіюйте лише `.db`, поки працює WAL).

### Widget sandbox

`app/widgets/renderer.py` — експериментальний статичний HTML-рендерер. Попередній перегляд:

```bash
.venv/bin/python -m app.widgets.preview
```

Відкрийте `data/widget_preview.html` у браузері. **Telegram Bot API не має підтвердженого способу доставки цього widget-sandbox HTML як native messageMediaWidget**. Тому v1.0 не видає preview за реально інтегрований Telegram-віджет. Поточний інтерфейс — звичайні повідомлення, кнопки та текстова heatmap.

## Межі v1.0

- Відсутність heartbeat ≠ доведена відсутність електрики.
- `/heatmap` текстова, без графічного рендеру.
- Ручне коригування подій, точна оцінка часу відновлення світла та окремий датчик 230 В ще не реалізовані.
- Якщо RPi знеструмлено, Telegram-бот не надсилає повідомлення в реальному часі.
- Після зміни `.env` перезапустіть відповідні сервіси.
- Для production варто додати регулярний SQLite backup, watchdog та моніторинг стану накопичувача.

## Оновлення

Не видаляйте `.env` та `data/`. Зупиніть сервіси перед заміною файлів. Зберігайте лише один `README.md`.
