"""Pillow-only PNG cards for Telegram. No website, widget, or HTTPS."""
from __future__ import annotations
import io
import calendar
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .config import TZ
from .database import connect, utc_now, setting
from .statistics import daily, summary, local_bounds, format_duration, day_timeline
from .health import snapshot as health_snapshot

W = 960
BG='#111217'; CARD='#1b2027'; WHITE='#f4f6f8'; MUTED='#a1acbb'
GREEN='#56A64B'; RED='#e57373'; AMBER='#e7b566'; GREY='#48515d'; FUTURE='#292e36'; EDGE='#343b45'
FONT_DIR=Path('/usr/share/fonts/truetype/dejavu'); WIN_DIR=Path('C:/Windows/Fonts')

def font(size,bold=False):
    candidates = ([WIN_DIR/'arialbd.ttf',FONT_DIR/'DejaVuSans-Bold.ttf'] if bold
                  else [WIN_DIR/'arial.ttf',FONT_DIR/'DejaVuSans.ttf'])
    for p in candidates:
        if p.exists(): return ImageFont.truetype(str(p),size)
    return ImageFont.load_default()

def txt(d,xy,value,size=23,color=WHITE,bold=False,anchor=None):
    d.text(xy,str(value),font=font(size,bold),fill=color,anchor=anchor)

def panel(d,rect): d.rounded_rectangle(rect,radius=23,fill=CARD)

def canvas(title,subtitle,height):
    im=Image.new('RGB',(W,height),BG);d=ImageDraw.Draw(im)
    txt(d,(48,38),'AYLA  /  POWER MONITOR',24,GREEN,True)
    txt(d,(48,85),title,44,WHITE,True)
    txt(d,(48,151),subtitle,22,MUTED)
    return im,d

def footer(d,height):
    txt(d,(48,height-62),'Дані: heartbeat Raspberry Pi · Europe/Kyiv',18,MUTED)
    txt(d,(48,height-34),'Без сигналу ≠ підтверджене відключення світла',18,AMBER)

def png(im):
    buf=io.BytesIO();im.save(buf,'PNG',optimize=True);return buf.getvalue()

def stats(d,record,y=216):
    total=record['total']; observed=record['observed'];unknown=record['unknown']
    for x,title,secs,color in ((48,'Є СИГНАЛ',observed,GREEN),(492,'НЕВІДОМО',unknown,RED)):
        panel(d,(x,y,x+420,y+183))
        txt(d,(x+23,y+23),title,20,MUTED,True)
        txt(d,(x+23,y+73),format_duration(secs),34,color,True)
        txt(d,(x+23,y+139),f'{secs/total*100:.1f}% минулого часу' if total else 'Немає даних',18,MUTED)

def timeline(d, bins, x, y, width, height):
    """Three distinct colors: observed, unobserved, and future."""
    cell=width/len(bins)
    for i,(obs,unk,future) in enumerate(bins):
        total=obs+unk+future
        if total <= 0: continue
        xx=x+i*cell
        ww=max(1,int(cell)-2)
        # Each vertical stripe can have mixed coverage; green at top, red below, future at bottom.
        h1=round(height*obs/total)
        h2=round(height*unk/total)
        if h1: d.rectangle((xx,y,xx+ww,y+h1),fill=GREEN)
        if h2: d.rectangle((xx,y+h1,xx+ww,y+h1+h2),fill=RED)
        if h1+h2<height: d.rectangle((xx,y+h1+h2,xx+ww,y+height),fill=FUTURE)

def timeline_labels(d,x,y,width):
    for hour in (0,6,12,18,24):
        txt(d,(x+width*hour/24,y),f'{hour:02d}:00',18,MUTED,anchor='mt' if hour else 'lt')

def legend(d,y):
    for x,color,name in ((75,GREEN,'Сигнал'),(310,RED,'Невідомо'),(582,FUTURE,'Майбутнє')):
        d.rounded_rectangle((x,y,x+20,y+20),radius=4,fill=color)
        txt(d,(x+30,y-4),name,19,MUTED)

def gaps(limit=5):
    with connect() as db:
        return [dict(r) for r in db.execute(
            'SELECT started_at,ended_at,seconds FROM gaps ORDER BY started_at DESC LIMIT ?',
            (limit,)).fetchall()]

def render_today():
    now=utc_now().astimezone(TZ);day=now.date();record=daily(day)
    im,d=canvas('Сьогодні',f'{day:%d.%m.%Y} · до {now:%H:%M} за Києвом',1170)
    stats(d,record)
    panel(d,(48,425,912,747))
    txt(d,(75,452),'ШКАЛА ДОБИ · 30-ХВ ІНТЕРВАЛИ',23,WHITE,True)
    timeline(d,day_timeline(day,48),75,511,812,128)
    timeline_labels(d,75,654,812)
    legend(d,700)
    panel(d,(48,765,912,1051))
    txt(d,(75,790),'ОСТАННІ РОЗРИВИ СПОСТЕРЕЖЕННЯ',22,WHITE,True)
    rows=gaps(4)
    if not rows: txt(d,(77,858),'Зафіксованих розривів немає',24,MUTED)
    for i,row in enumerate(rows):
        y=850+i*49
        when=datetime.fromisoformat(row['started_at']).astimezone(TZ)
        txt(d,(78,y),f'{when:%d.%m  %H:%M}',23)
        txt(d,(884,y),format_duration(row['seconds']),23,RED,anchor='ra')
    footer(d,1170)
    return png(im)

def render_week():
    today=utc_now().astimezone(TZ).date()
    days=[today-timedelta(days=i) for i in range(6,-1,-1)]
    items=[(day,daily(day)) for day in days]
    total=sum(r['total'] for _,r in items);observed=sum(r['observed'] for _,r in items)
    im,d=canvas('Останні 7 днів','Тривалість і розподіл сигналу за днями',1390)
    stats(d,{'total':total,'observed':observed,'unknown':total-observed})
    panel(d,(48,425,912,1258))
    txt(d,(74,451),'30-ХВ ШКАЛИ',23,WHITE,True)
    txt(d,(884,453),'СИГНАЛ / НЕВІДОМО',17,MUTED,True,anchor='ra')
    for i,(day,rec) in enumerate(items):
        y=504+i*99
        txt(d,(76,y),f'{day:%d.%m}',22,WHITE,True)
        txt(d,(884,y),f'{format_duration(rec["observed"])} / {format_duration(rec["unknown"])}',19,GREEN,anchor='ra')
        timeline(d,day_timeline(day,48),76,y+37,808,32)
    legend(d,1212)
    footer(d,1390)
    return png(im)

def render_month():
    today=utc_now().astimezone(TZ).date();first=today.replace(day=1)
    start,_=local_bounds(first);record=summary(start,utc_now())
    im,d=canvas('Поточний місяць',f'{today:%m.%Y} · майбутні дні не враховано',1100)
    stats(d,record)
    panel(d,(48,425,912,976))
    txt(d,(76,452),'КАЛЕНДАР СПОСТЕРЕЖЕННЯ',22,WHITE,True)
    names=('ПН','ВТ','СР','ЧТ','ПТ','СБ','НД')
    for i,name in enumerate(names): txt(d,(115+i*116,516),name,19,MUTED,True,anchor='mt')
    count=calendar.monthrange(today.year,today.month)[1]
    for n in range(1,count+1):
        date=first.replace(day=n);idx=first.weekday()+n-1
        x=74+(idx%7)*116;y=550+(idx//7)*68
        if date>today: color=FUTURE
        else:
            rec=daily(date)
            frac=rec['observed']/rec['total'] if rec['total'] else 0
            color=GREEN if frac>=.8 else '#807a45' if frac>=.35 else '#78464a'
        d.rounded_rectangle((x,y,x+81,y+55),radius=12,fill=color)
        txt(d,(x+40,y+27),n,22,WHITE,True,anchor='mm')
    txt(d,(78,938),'Колір = частка сигналу за минулий час доби',18,MUTED)
    footer(d,1100);return png(im)

def render_history():
    im,d=canvas('Історія розривів','Останні інтервали без heartbeat',1090)
    panel(d,(48,210,912,970))
    txt(d,(76,242),'ПОЧАТОК',20,MUTED,True)
    txt(d,(882,242),'ТРИВАЛІСТЬ',20,MUTED,True,anchor='ra')
    rows=gaps(11)
    if not rows: txt(d,(78,310),'Розривів поки немає',25,MUTED)
    for i,row in enumerate(rows):
        y=300+i*58
        if i: d.line((76,y-12,882,y-12),fill=EDGE,width=2)
        when=datetime.fromisoformat(row['started_at']).astimezone(TZ)
        txt(d,(78,y),f'{when:%d.%m.%Y  %H:%M}',22)
        txt(d,(882,y),format_duration(row['seconds']),22,RED,anchor='ra')
    footer(d,1090);return png(im)

def render_health():
    h=health_snapshot()
    im,d=canvas('Стан Raspberry Pi',f'Діагностика · {h["sampled_at"]:%d.%m.%Y %H:%M}',1010)
    panel(d,(48,213,912,894))
    status='Працює' if h['active'] else ('Тестовий Windows' if h['system']=='Windows' else 'Немає свіжого сигналу')
    uptime=format_duration(h['uptime']) if h['uptime'] is not None else 'Недоступно'
    last=h['last'].astimezone(TZ).strftime('%d.%m.%Y %H:%M:%S') if h['last'] else 'Немає'
    rows=[('АГЕНТ',status),('СИСТЕМА',h['system']),('ОСТАННІЙ HEARTBEAT',last),
          ('ВІК СИГНАЛУ',f'{int(h["age"])} с' if h['age'] is not None else 'Немає'),
          ('UPTIME ПРИСТРОЮ',uptime),('СИНХРОНІЗАЦІЯ ЧАСУ',h['ntp']),
          ('SQLITE', 'OK' if h['db_ok'] else 'ПОМИЛКА'),
          ('ВІЛЬНО НА ДИСКУ',f'{h["disk_free_gb"]:.1f} ГБ'),
          ('СЕСІЇ / РОЗРИВИ',f'{h["sessions"]} / {h["gaps"]}')]
    for i,(label,value) in enumerate(rows):
        y=247+i*67
        txt(d,(76,y),label,19,MUTED,True)
        txt(d,(882,y),value,20,GREEN if label=='SQLITE' and h['db_ok'] else WHITE,anchor='ra')
        if i<len(rows)-1:d.line((76,y+45,882,y+45),fill=EDGE,width=2)
    footer(d,1010);return png(im)

def render_settings():
    im,d=canvas('Налаштування','Керування через кнопки Telegram',770)
    panel(d,(48,213,912,650))
    rows=[('СПОВІЩЕННЯ ПРО РОЗРИВИ','Увімкнено' if setting('notify','1')=='1' else 'Вимкнено'),
          ('ЩОДЕННИЙ ЗВІТ','Увімкнено' if setting('daily_report','1')=='1' else 'Вимкнено'),
          ('ЧАС ЗВІТУ','00:10 за Києвом, за вчора'),
          ('ПРИСТРІЙ','Raspberry Pi · один main.py')]
    for i,(name,value) in enumerate(rows):
        y=255+i*94
        txt(d,(76,y),name,19,MUTED,True)
        txt(d,(76,y+34),value,24,WHITE)
    footer(d,770);return png(im)

RENDERERS={'today':render_today,'week':render_week,'month':render_month,
           'history':render_history,'health':render_health,'settings':render_settings}

def render(section):
    return RENDERERS.get(section,render_today)()

def render_daily_report(day):
    """Report for a completed local date, independent of the current dashboard."""
    rec=daily(day)
    im,d=canvas('Підсумок дня',f'{day:%d.%m.%Y} · завершена доба',800)
    stats(d,rec)
    panel(d,(48,425,912,672))
    txt(d,(76,451),'ШКАЛА ДОБИ',23,WHITE,True)
    timeline(d,day_timeline(day,48),76,505,807,99)
    timeline_labels(d,76,620,807)
    footer(d,800)
    return png(im)
