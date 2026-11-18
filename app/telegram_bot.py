"""Telegram-first interface: image dashboards and inline buttons, no widget permission required."""
import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from .config import BOT_TOKEN, ADMIN_IDS, CHAT_ID, TZ
from .database import init, connect, utc_now, setting, set_setting
from .statistics import daily, summary, format_duration, local_bounds
from .dashboard import render

LOG=logging.getLogger(__name__)
SECTIONS={'today':'Сьогодні','week':'7 днів','month':'Місяць','history':'Історія'}
COMMANDS=[('start','Відкрити дашборд'),('dashboard','Дашборд'),('help','Команди'),
 ('status','Стан агента'),('today','Сьогодні'),('yesterday','Вчора'),
 ('week','Останні 7 днів'),('month','Місяць'),('history','Розриви'),
 ('heatmap','Теплова карта'),('export','Експорт CSV'),('settings','Налаштування')]


def authorized(update):
    u=update.effective_user
    return bool(u and u.id in ADMIN_IDS)

async def guard(update):
    if authorized(update):return True
    if update.callback_query:await update.callback_query.answer('⛔ Немає доступу',show_alert=True)
    else:await update.effective_message.reply_text('⛔ Немає доступу. Перевір TELEGRAM_ADMIN_IDS у .env.')
    return False


def buttons(section):
    rows=[]
    keys=list(SECTIONS)
    for a,b in [('today','week'),('month','history')]:
        rows.append([InlineKeyboardButton(('• ' if section==k else '')+SECTIONS[k],callback_data='dash:'+k) for k in (a,b)])
    rows.append([InlineKeyboardButton('🔄 Оновити',callback_data='dash:'+section+':refresh'),
                 InlineKeyboardButton('⚙️ Стан',callback_data='dash:status')])
    return InlineKeyboardMarkup(rows)


def caption(section):
    now=utc_now().astimezone(TZ)
    return f'⚡ Ayla Power Monitor · {SECTIONS[section]}\n🕒 {now:%d.%m.%Y %H:%M} · Київ\nℹ️ Не вимірює електрику напряму'

async def dashboard(update,ctx,section='today'):
    if not await guard(update):return
    if section not in SECTIONS:section='today'
    data=await asyncio.to_thread(render,section)
    file=InputFile(io.BytesIO(data),filename='ayla_dashboard.png')
    if update.callback_query:
        q=update.callback_query
        try:
            await q.edit_message_media(media=InputMediaPhoto(media=file,caption=caption(section)),reply_markup=buttons(section))
        except BadRequest as exc:
            if 'message is not modified' not in str(exc).lower():
                LOG.warning('Cannot edit dashboard; sending fresh one: %s',exc)
                await q.message.reply_photo(photo=file,caption=caption(section),reply_markup=buttons(section))
    else:
        await update.effective_message.reply_photo(photo=file,caption=caption(section),reply_markup=buttons(section))

async def start(u,c):await dashboard(u,c)
async def today(u,c):await dashboard(u,c,'today')
async def week(u,c):await dashboard(u,c,'week')
async def month(u,c):await dashboard(u,c,'month')
async def history(u,c):await dashboard(u,c,'history')
async def heatmap(u,c):await dashboard(u,c,'month')

async def help_cmd(u,c):
    if not await guard(u):return
    await u.effective_message.reply_text('⚡ Ayla Power Monitor\n\n'+'\n'.join(f'/{k} — {v}' for k,v in COMMANDS)+'\n\n📊 /dashboard — інтерактивний дашборд')

async def status(u,c):
    if not await guard(u):return
    with connect() as db:r=db.execute('SELECT * FROM state WHERE id=1').fetchone()
    if not r:message='⚪ Ще немає heartbeat від агента.'
    else:
        last=datetime.fromisoformat(r['last_seen'])
        age=max(0,(utc_now()-last).total_seconds())
        message=(f"{'🟢' if age<40 else '🟠'} Агент: {'активний' if age<40 else 'сигнал застарів'}\n"
                 f'Останній heartbeat: {last.astimezone(TZ):%d.%m.%Y %H:%M:%S}\n'
                 f'Час від останнього сигналу: {int(age)} с')
    if u.callback_query:await u.callback_query.message.reply_text(message)
    else:await u.effective_message.reply_text(message)

async def yesterday(u,c):
    if not await guard(u):return
    day=utc_now().astimezone(TZ).date()-timedelta(days=1);s=daily(day)
    pct=100*s['observed']/s['total'] if s['total'] else 0
    await u.effective_message.reply_text(f'📅 Вчора · {day:%d.%m.%Y}\n🟢 Спостереження: {format_duration(s["observed"])} ({pct:.1f}%)\n⚪ Невідомо: {format_duration(s["unknown"])}')

async def export(u,c):
    if not await guard(u):return
    with connect() as db:rows=db.execute('SELECT started_at,ended_at,seconds,kind,note FROM gaps ORDER BY started_at').fetchall()
    out=io.StringIO();w=csv.writer(out);w.writerow(['started_at_utc','ended_at_utc','seconds','kind','note'])
    for row in rows:w.writerow(tuple(row))
    buffer=io.BytesIO(out.getvalue().encode('utf-8-sig'))
    await u.effective_message.reply_document(document=InputFile(buffer,filename='ayla_power_gaps.csv'))

async def settings(u,c):
    if not await guard(u):return
    await u.effective_message.reply_text('⚙️ Ayla Power Monitor\nЧасовий пояс: Europe/Kyiv\nСповіщення: '+('увімкнено' if setting('notify','1')=='1' else 'вимкнено')+'\n/notify_on · /notify_off')

async def notify(u,c):
    if not await guard(u):return
    enabled=u.effective_message.text.startswith('/notify_on')
    set_setting('notify','1' if enabled else '0')
    await u.effective_message.reply_text('Сповіщення '+('увімкнено' if enabled else 'вимкнено'))

async def callbacks(u,c):
    if not await guard(u):return
    q=u.callback_query
    await q.answer()
    parts=(q.data or '').split(':')
    if len(parts)<2 or parts[0]!='dash':return
    if parts[1]=='status':return await status(u,c)
    if parts[1] in SECTIONS:return await dashboard(u,c,parts[1])

async def post_init(app):
    await app.bot.set_my_commands([BotCommand(cmd,desc) for cmd,desc in COMMANDS])
    # Send gaps recorded while monitor was offline. Notification must not claim proven power loss.
    if not CHAT_ID or setting('notify','1')!='1':return
    with connect() as db:rows=db.execute('SELECT id,seconds FROM gaps WHERE notified=0 ORDER BY id LIMIT 20').fetchall()
    for row in rows:
        try:
            await app.bot.send_message(CHAT_ID,f'⚠️ Зафіксовано розрив спостереження: {format_duration(row["seconds"])}. Причина невідома.')
            with connect() as db:db.execute('UPDATE gaps SET notified=1 WHERE id=?',(row['id'],))
        except TelegramError:LOG.exception('Cannot send gap alert');break


def main():
    if not BOT_TOKEN:raise SystemExit('Вкажи TELEGRAM_BOT_TOKEN у .env')
    if not ADMIN_IDS:raise SystemExit('Вкажи TELEGRAM_ADMIN_IDS у .env')
    init()
    logging.basicConfig(level=logging.INFO)
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    mapping=[('start',start),('dashboard',start),('help',help_cmd),('status',status),
             ('today',today),('yesterday',yesterday),('week',week),('month',month),
             ('history',history),('heatmap',heatmap),('export',export),('settings',settings),
             ('notify_on',notify),('notify_off',notify)]
    for name,callback in mapping:app.add_handler(CommandHandler(name,callback))
    app.add_handler(CallbackQueryHandler(callbacks,pattern='^dash:'))
    LOG.info('Telegram Dashboard ready (no sendWidget / web server)')
    app.run_polling(drop_pending_updates=True)

if __name__=='__main__':main()
