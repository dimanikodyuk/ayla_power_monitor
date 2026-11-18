import asyncio
import csv
import io
import logging
from datetime import timedelta
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from .config import BOT_TOKEN, ADMIN_IDS, CHAT_ID, TZ
from .database import init, connect, utc_now, setting, set_setting
from .statistics import daily, summary, format_duration, local_bounds, get_gaps

LOG=logging.getLogger(__name__)
COMMANDS=[
("start","Головне меню"),("help","Список команд"),("status","Стан моніторингу"),
("today","Статистика сьогодні"),("yesterday","Статистика вчора"),
("week","Останні 7 днів"),("month","Поточний місяць"),
("history","Історія розривів"),("heatmap","Теплова карта за тиждень"),
("export","Експорт CSV"),("settings","Налаштування")
]
HELP="⚡ Ayla Power Monitor\\n\\n"+ "\\n".join(f"/{a} — {b}" for a,b in COMMANDS)+"\\n\\nℹ️ Розриви моніторингу не доводять відсутність електрики."

def authorized(update):
    user=update.effective_user
    return bool(user and ADMIN_IDS and user.id in ADMIN_IDS)

async def send(update, text, **kw):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text,**kw)
    else:
        await update.effective_message.reply_text(text,**kw)

async def guard(update):
    if not authorized(update):
        await send(update,"⛔ Немає доступу. Додайте ваш Telegram user ID до TELEGRAM_ADMIN_IDS.")
        return False
    return True

async def start(update,ctx):
    if not await guard(update): return
    keys=[[InlineKeyboardButton("📊 Сьогодні",callback_data="today"),InlineKeyboardButton("📅 Тиждень",callback_data="week")],
          [InlineKeyboardButton("❓ Допомога",callback_data="help"),InlineKeyboardButton("📜 Історія",callback_data="history")]]
    await send(update,"⚡ Ayla Power Monitor\\nМоніторинг Raspberry Pi та статистика розривів.",reply_markup=InlineKeyboardMarkup(keys))

async def help_cmd(update,ctx):
    if await guard(update): await send(update,HELP.replace("\\n","\n"))

async def status(update,ctx):
    if not await guard(update): return
    with connect() as db:
        r=db.execute("SELECT * FROM state WHERE id=1").fetchone()
    if not r:
        await send(update,"Моніторинг ще не записав heartbeat.");return
    from datetime import datetime
    last=datetime.fromisoformat(r["last_seen"])
    age=(utc_now()-last).total_seconds()
    await send(update,f"⚡ Агент: {'🟢 працює' if age<40 else '⚠️ немає свіжого сигналу'}\nОстанній heartbeat: {last.astimezone(TZ):%d.%m.%Y %H:%M:%S}\nВік сигналу: {max(0,int(age))} с")

def stats_text(label,s):
    total=s["total"]
    pct=s["observed"]/total*100 if total else 0
    return f"📊 {label}\n🟢 Моніторинг активний: {format_duration(s['observed'])} ({pct:.1f}%)\n⚪ Немає спостереження: {format_duration(s['unknown'])}\nℹ️ Це не прямий вимір наявності світла."

async def today(update,ctx):
    if await guard(update):
        await send(update,stats_text("Сьогодні",daily(utc_now().astimezone(TZ).date())))

async def yesterday(update,ctx):
    if await guard(update):
        await send(update,stats_text("Вчора",daily(utc_now().astimezone(TZ).date()-timedelta(days=1))))

async def week(update,ctx):
    if not await guard(update):return
    day=utc_now().astimezone(TZ).date()
    lines=["📅 Останні 7 днів"]
    for offset in range(6,-1,-1):
        d=day-timedelta(days=offset)
        s=daily(d)
        lines.append(f"{d:%d.%m}: 🟢 {format_duration(s['observed'])} · ⚪ {format_duration(s['unknown'])}")
    await send(update,"\n".join(lines))

async def month(update,ctx):
    if not await guard(update):return
    day=utc_now().astimezone(TZ).date()
    start,_=local_bounds(day.replace(day=1))
    await send(update,stats_text(f"Місяць {day:%m.%Y}",summary(start,utc_now())))

async def history(update,ctx):
    if not await guard(update):return
    with connect() as db:
        rows=db.execute("SELECT * FROM gaps ORDER BY id DESC LIMIT 12").fetchall()
    if not rows: await send(update,"Розривів поки немає.");return
    from datetime import datetime
    lines=["📜 Останні розриви моніторингу"]
    for r in rows:
        t=datetime.fromisoformat(r["started_at"]).astimezone(TZ)
        lines.append(f"{t:%d.%m %H:%M} · {format_duration(r['seconds'])} · {r['kind']}")
    await send(update,"\n".join(lines))

async def heatmap(update,ctx):
    if not await guard(update):return
    # Text heatmap avoids image dependency and works in any Telegram client.
    day=utc_now().astimezone(TZ).date()
    lines=["🗓 Heatmap (🟩 спостерігалось / ⬜ невідомо)","       00  04  08  12  16  20"]
    for offset in range(6,-1,-1):
        d=day-timedelta(days=offset)
        start,_=local_bounds(d)
        cells=[]
        for h in range(0,24,4):
            a=start+timedelta(hours=h)
            b=a+timedelta(hours=4)
            s=summary(a,b)
            cells.append("🟩" if s["total"] and s["observed"]/s["total"]>=.9 else "⬜")
        lines.append(f"{d:%d.%m} "+ "".join(cells))
    await send(update,"\n".join(lines))

async def export(update,ctx):
    if not await guard(update):return
    with connect() as db:
        rows=db.execute("SELECT started_at,ended_at,seconds,kind,note FROM gaps ORDER BY started_at").fetchall()
    f=io.StringIO()
    writer=csv.writer(f)
    writer.writerow(["started_at_utc","ended_at_utc","seconds","kind","note"])
    for r in rows: writer.writerow(list(r))
    bio=io.BytesIO(f.getvalue().encode("utf-8-sig"))
    bio.name="ayla_power_gaps.csv"
    await update.effective_message.reply_document(document=InputFile(bio,filename=bio.name))

async def settings(update,ctx):
    if not await guard(update):return
    await send(update,"⚙️ Налаштування v1.0\nЧасовий пояс: Europe/Kyiv\nІнтервал heartbeat: задається у .env\nСповіщення про розриви: "+("увімкнено" if setting("notify","1")=="1" else "вимкнено")+"\nКоманди: /notify_on /notify_off")

async def notify(update,ctx):
    if not await guard(update):return
    enabled=update.effective_message.text.strip().startswith("/notify_on")
    set_setting("notify","1" if enabled else "0")
    await send(update,"Сповіщення "+("увімкнено" if enabled else "вимкнено"))

async def callbacks(update,ctx):
    command=update.callback_query.data
    handlers={"today":today,"week":week,"help":help_cmd,"history":history}
    if command in handlers: await handlers[command](update,ctx)

async def post_init(app):
    await app.bot.set_my_commands([BotCommand(a,b) for a,b in COMMANDS])
    # Send only previously recorded, not-yet-notified gaps; never invent outage claims.
    if not CHAT_ID or setting("notify","1")!="1":return
    with connect() as db:
        rows=db.execute("SELECT id,started_at,seconds FROM gaps WHERE notified=0 ORDER BY id LIMIT 20").fetchall()
    for r in rows:
        try:
            await app.bot.send_message(chat_id=CHAT_ID,text=f"⚠️ Виявлено розрив моніторингу: {format_duration(r['seconds'])}. Причина невідома.")
            with connect() as db: db.execute("UPDATE gaps SET notified=1 WHERE id=?",(r["id"],))
        except Exception: LOG.exception("Notification delivery failed");break

def main():
    if not BOT_TOKEN: raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    if not ADMIN_IDS: raise SystemExit("Set TELEGRAM_ADMIN_IDS in .env")
    init()
    logging.basicConfig(level=logging.INFO)
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    for name,fn in [("start",start),("help",help_cmd),("status",status),("today",today),
                    ("yesterday",yesterday),("week",week),("month",month),
                    ("history",history),("heatmap",heatmap),("export",export),
                    ("settings",settings),("notify_on",notify),("notify_off",notify)]:
        app.add_handler(CommandHandler(name,fn))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
