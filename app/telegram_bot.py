"""Telegram-only photo dashboards, notifications and durable daily reports."""
from __future__ import annotations
import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta, time as dt_time
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from .config import BOT_TOKEN, ADMIN_IDS, CHAT_ID, TZ
from .database import init, connect, utc_now, setting, set_setting
from .statistics import daily, format_duration
from .dashboard import render, render_daily_report
from .health import snapshot as health_snapshot

LOG=logging.getLogger(__name__)
SECTIONS={'today':'Сьогодні','week':'7 днів','month':'Місяць',
          'history':'Історія','health':'Здоровʼя Pi','settings':'Налаштування'}
COMMANDS=[('start','Відкрити дашборд'),('dashboard','Дашборд'),
 ('today','Сьогодні'),('week','Останні 7 днів'),('month','Поточний місяць'),
 ('history','Історія розривів'),('health','Стан Raspberry Pi'),
 ('status','Діагностика текстом'),('yesterday','Учора'),
 ('settings','Налаштування'),('export','Експорт CSV'),('help','Допомога')]


def authorized(update):
    user=update.effective_user
    return bool(user and user.id in ADMIN_IDS)

async def guard(update):
    if authorized(update):return True
    if update.callback_query:
        await update.callback_query.answer('⛔ Немає доступу',show_alert=True)
    else:
        await update.effective_message.reply_text('⛔ Немає доступу. Перевір TELEGRAM_ADMIN_IDS у .env.')
    return False


def keyboard(section):
    rows=[]
    for pair in (('today','week'),('month','history'),('health','settings')):
        rows.append([InlineKeyboardButton(('• ' if section==key else '')+SECTIONS[key],
                                          callback_data='dash:'+key) for key in pair])
    if section=='settings':
        notify=setting('notify','1')=='1'; daily=setting('daily_report','1')=='1'
        rows.append([InlineKeyboardButton('🔔 Сповіщення: '+('ON' if notify else 'OFF'),callback_data='toggle:notify')])
        rows.append([InlineKeyboardButton('📅 Звіти: '+('ON' if daily else 'OFF'),callback_data='toggle:daily_report')])
    rows.append([InlineKeyboardButton('🔄 Оновити',callback_data='dash:'+section)])
    return InlineKeyboardMarkup(rows)


def caption(section):
    now=utc_now().astimezone(TZ)
    return (f'⚡ Ayla Power Monitor · {SECTIONS[section]}\n'
            f'🕒 {now:%d.%m.%Y %H:%M} · Київ\n'
            'ℹ️ Моніторинг heartbeat, не вимірювання напруги')

async def dashboard(update,ctx,section='today'):
    if not await guard(update):return
    section=section if section in SECTIONS else 'today'
    data=await asyncio.to_thread(render,section)
    if update.callback_query:
        q=update.callback_query
        try:
            await q.edit_message_media(
                media=InputMediaPhoto(media=InputFile(io.BytesIO(data),filename='ayla_dashboard.png'),
                                      caption=caption(section)),
                reply_markup=keyboard(section))
        except BadRequest as exc:
            if 'message is not modified' not in str(exc).lower():
                LOG.warning('Cannot edit photo; sending a new one: %s',exc)
                await q.message.reply_photo(
                    photo=InputFile(io.BytesIO(data),filename='ayla_dashboard.png'),
                    caption=caption(section),reply_markup=keyboard(section))
    else:
        await update.effective_message.reply_photo(
            photo=InputFile(io.BytesIO(data),filename='ayla_dashboard.png'),
            caption=caption(section),reply_markup=keyboard(section))

async def start(u,c):await dashboard(u,c)
async def today(u,c):await dashboard(u,c,'today')
async def week(u,c):await dashboard(u,c,'week')
async def month(u,c):await dashboard(u,c,'month')
async def history(u,c):await dashboard(u,c,'history')
async def health(u,c):await dashboard(u,c,'health')
async def settings(u,c):await dashboard(u,c,'settings')
async def heatmap(u,c):await dashboard(u,c,'month')

async def help_cmd(u,c):
    if not await guard(u):return
    await u.effective_message.reply_text('⚡ Ayla Power Monitor\n\n'+
        '\n'.join(f'/{name} — {desc}' for name,desc in COMMANDS)+
        '\n/notify_on · /notify_off · /daily_on · /daily_off')

async def status(u,c):
    if not await guard(u):return
    h=await asyncio.to_thread(health_snapshot)
    last=h['last'].astimezone(TZ).strftime('%d.%m.%Y %H:%M:%S') if h['last'] else 'немає'
    message=(f"{'🟢' if h['active'] else '🟠'} Агент: {'активний' if h['active'] else 'без свіжого heartbeat'}\n"
             f'Останній сигнал: {last}\n'
             f"Вік сигналу: {int(h['age']) if h['age'] is not None else '—'} с\n"
             f"Система: {h['system']}\nNTP: {h['ntp']}\n"
             f"SQLite: {'OK' if h['db_ok'] else 'ПОМИЛКА'}\n"
             f"Вільно: {h['disk_free_gb']:.1f} ГБ")
    if u.callback_query:await u.callback_query.message.reply_text(message)
    else:await u.effective_message.reply_text(message)

async def yesterday(u,c):
    if not await guard(u):return
    day=utc_now().astimezone(TZ).date()-timedelta(days=1)
    rec=daily(day)
    await u.effective_message.reply_photo(
        photo=InputFile(io.BytesIO(await asyncio.to_thread(render_daily_report,day)),
                        filename='ayla_yesterday.png'),
        caption=f'📅 Учора · {day:%d.%m.%Y}\n'
                f'🟢 {format_duration(rec["observed"])} · ⚪ {format_duration(rec["unknown"])}')

async def export(u,c):
    if not await guard(u):return
    with connect() as db:
        rows=db.execute('SELECT started_at,ended_at,seconds,kind,note FROM gaps ORDER BY started_at').fetchall()
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['started_at_utc','ended_at_utc','seconds','kind','note'])
    for row in rows:writer.writerow(tuple(row))
    await u.effective_message.reply_document(
        document=InputFile(io.BytesIO(out.getvalue().encode('utf-8-sig')),
                           filename='ayla_power_gaps.csv'))

async def toggle_cmd(u,c):
    if not await guard(u):return
    cmd=u.effective_message.text.split()[0].split('@')[0]
    key='daily_report' if cmd.startswith('/daily_') else 'notify'
    enabled=cmd.endswith('_on')
    set_setting(key,'1' if enabled else '0')
    await u.effective_message.reply_text(
        ('Щоденний звіт' if key=='daily_report' else 'Сповіщення')+
        (' увімкнено' if enabled else ' вимкнено'))

async def callbacks(u,c):
    if not await guard(u):return
    q=u.callback_query
    await q.answer()
    parts=(q.data or '').split(':')
    if len(parts)!=2:return
    if parts[0]=='dash' and parts[1] in SECTIONS:
        await dashboard(u,c,parts[1])
    elif parts[0]=='toggle' and parts[1] in ('notify','daily_report'):
        key=parts[1]
        set_setting(key,'0' if setting(key,'1')=='1' else '1')
        await dashboard(u,c,'settings')

async def _deliver_gaps(app):
    if not CHAT_ID or setting('notify','1')!='1':return
    with connect() as db:
        rows=db.execute('SELECT id,seconds,started_at,ended_at FROM gaps '
                        'WHERE notified=0 ORDER BY id LIMIT 20').fetchall()
    for row in rows:
        started=datetime.fromisoformat(row['started_at']).astimezone(TZ)
        ended=datetime.fromisoformat(row['ended_at']).astimezone(TZ)
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=f'⚡ Моніторинг відновився\n'
                 f'🔴 Без сигналу: {format_duration(row["seconds"])}\n'
                 f'🕒 {started:%d.%m %H:%M} — {ended:%d.%m %H:%M}\n'
                 'ℹ️ Причина розриву невідома; це не доказ відключення світла.')
        with connect() as db:
            db.execute('UPDATE gaps SET notified=1 WHERE id=?',(row['id'],))

async def _deliver_daily(app):
    if not CHAT_ID or setting('daily_report','1')!='1':return
    now=utc_now().astimezone(TZ)
    if now.time()<dt_time(0,10):return
    day=now.date()-timedelta(days=1)
    if setting('daily_last_sent','')>=day.isoformat():return
    data=await asyncio.to_thread(render_daily_report,day)
    rec=daily(day)
    await app.bot.send_photo(
        chat_id=CHAT_ID,photo=InputFile(io.BytesIO(data),filename='ayla_daily.png'),
        caption=f'📅 Підсумок за {day:%d.%m.%Y}\n'
                f'🟢 Сигнал: {format_duration(rec["observed"])}\n'
                f'⚪ Невідомо: {format_duration(rec["unknown"])}\n'
                'Дані heartbeat, не показання електролічильника.')
    set_setting('daily_last_sent',day.isoformat())

async def _background(app):
    while True:
        for job in (_deliver_gaps,_deliver_daily):
            try:
                await job(app)
            except TelegramError:
                LOG.exception('Telegram delivery failed; will retry')
            except Exception:
                LOG.exception('Background delivery failed; will retry')
        await asyncio.sleep(30)

async def post_init(app):
    await app.bot.set_my_commands([BotCommand(cmd,desc) for cmd,desc in COMMANDS])
    app.bot_data['delivery_task']=asyncio.create_task(_background(app),name='ayla-delivery')

async def post_stop(app):
    task=app.bot_data.get('delivery_task')
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass


def main():
    if not BOT_TOKEN:raise SystemExit('Вкажи TELEGRAM_BOT_TOKEN у .env')
    if not ADMIN_IDS:raise SystemExit('Вкажи TELEGRAM_ADMIN_IDS у .env')
    init()
    app=(Application.builder().token(BOT_TOKEN)
         .post_init(post_init).post_stop(post_stop).build())
    handlers=[('start',start),('dashboard',start),('help',help_cmd),('status',status),
              ('today',today),('yesterday',yesterday),('week',week),('month',month),
              ('history',history),('heatmap',heatmap),('health',health),('settings',settings),
              ('export',export),('notify_on',toggle_cmd),('notify_off',toggle_cmd),
              ('daily_on',toggle_cmd),('daily_off',toggle_cmd)]
    for name,fn in handlers:app.add_handler(CommandHandler(name,fn))
    app.add_handler(CallbackQueryHandler(callbacks,pattern='^(dash:|toggle:)'))
    LOG.info('Telegram v1.4 ready: no website or sendWidget')
    app.run_polling(drop_pending_updates=True)

if __name__=='__main__':main()
