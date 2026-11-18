"""Render lightweight Telegram dashboard images; all periods in Europe/Kyiv."""
from __future__ import annotations
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .config import TZ
from .database import connect, utc_now
from .statistics import daily, summary, local_bounds, format_duration

W=960
BG='#111217'; CARD='#1b2027'; EDGE='#333a45'; WHITE='#f4f6f8'; MUTED='#a1acbb'; GREEN='#56A64B'; RED='#ec7777'; AMBER='#e7b566'; GREY='#48515d'
FONT_DIR=Path('/usr/share/fonts/truetype/dejavu')
WIN_DIR=Path('C:/Windows/Fonts')

def font(sz, bold=False):
    candidates=([WIN_DIR/'arialbd.ttf', FONT_DIR/'DejaVuSans-Bold.ttf'] if bold else [WIN_DIR/'arial.ttf', FONT_DIR/'DejaVuSans.ttf'])
    for p in candidates:
        if p.exists(): return ImageFont.truetype(str(p),sz)
    return ImageFont.load_default()

def rounded(draw, box, fill=CARD, radius=24): draw.rounded_rectangle(box,radius=radius,fill=fill)
def text(d, xy, s, size=24, color=WHITE, bold=False, anchor=None):
    d.text(xy,str(s),fill=color,font=font(size,bold),anchor=anchor)

def base(title, subtitle, height=1120):
    im=Image.new('RGB',(W,height),BG);d=ImageDraw.Draw(im)
    text(d,(48,42),'AYLA  /  POWER MONITOR',25,GREEN,True)
    text(d,(48,91),title,45,WHITE,True)
    text(d,(48,157),subtitle,23,MUTED)
    return im,d

def footer(d,height):
    text(d,(48,height-57),'Дані: heartbeat Raspberry Pi · час Europe/Kyiv',18,MUTED)
    text(d,(48,height-31),'Пропуск сигналу ≠ доведене відключення електрики',18,AMBER)

def bars_for(day, slots=48):
    """Compute local-day slices in real timeline including DST boundaries."""
    a,b=local_bounds(day)
    step=(b-a)/slots
    values=[]
    for i in range(slots):
        s=summary(a+step*i,a+step*(i+1))
        values.append(s['observed']/s['total'] if s['total'] else 0)
    return values

def draw_grid(d, vals, x=55, y=494, width=850, height=142):
    count=len(vals);unit=width/count
    for i,v in enumerate(vals):
        col=GREEN if v>=.85 else AMBER if v>.15 else GREY
        x1=int(x+i*unit+1);x2=int(x+(i+1)*unit-2)
        d.rounded_rectangle((x1,y,x2,y+height),radius=3,fill=col)
    for h in (0,6,12,18,24):
        text(d,(x+width*h/24,y+height+15),f'{h:02d}:00',17,MUTED,anchor='mt' if h else 'lt')

def stat_cards(d, stats, top=230):
    total=stats['total']; observed=stats['observed'];unknown=stats['unknown'];percent=100*observed/total if total else 0
    for x,label,val,highlight,small in [
      (48,'Є СИГНАЛ',format_duration(observed),GREEN,f'{percent:.1f}% періоду'),
      (492,'НЕВІДОМО',format_duration(unknown),RED,f'{100-percent:.1f}% періоду' if total else 'Немає даних')]:
        rounded(d,(x,top,x+420,top+204));text(d,(x+25,top+23),label,21,MUTED,True)
        text(d,(x+25,top+76),val,35,highlight,True)
        text(d,(x+25,top+153),small,20,MUTED)

def recent_gaps(limit=5):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT started_at,ended_at,seconds FROM gaps ORDER BY started_at DESC LIMIT ?', (limit,)).fetchall()]

def render_today():
    day=utc_now().astimezone(TZ).date();s=daily(day)
    im,d=base('Сьогодні',f'{day:%d.%m.%Y}  ·  активність моніторингу',1160)
    stat_cards(d,s)
    rounded(d,(48,458,912,711));text(d,(76,475),'СТАН ЗА 24 ГОДИНИ',23,WHITE,True)
    draw_grid(d,bars_for(day),72,534,817,120)
    rounded(d,(48,733,912,1040));text(d,(76,755),'ОСТАННІ РОЗРИВИ СПОСТЕРЕЖЕННЯ',22,WHITE,True)
    gaps=recent_gaps(4)
    if not gaps: text(d,(78,821),'Розривів поки немає',26,MUTED)
    for i,g in enumerate(gaps):
        try: stamp=datetime.fromisoformat(g['started_at']).astimezone(TZ).strftime('%d.%m  %H:%M')
        except Exception: stamp='Невідомий час'
        y=813+i*50
        d.ellipse((77,y+12,89,y+24),fill=RED)
        text(d,(106,y),stamp,23,WHITE)
        text(d,(882,y),format_duration(g['seconds']),23,RED,anchor='ra')
    footer(d,1160)
    return png(im)

def render_week():
    day=utc_now().astimezone(TZ).date()
    im,d=base('Останні 7 днів','Порівняння активного спостереження',1100)
    items=[(day-timedelta(days=x),daily(day-timedelta(days=x))) for x in range(6,-1,-1)]
    total=sum(s['total'] for _,s in items);observed=sum(s['observed'] for _,s in items)
    stat_cards(d,{'total':total,'observed':observed,'unknown':total-observed})
    rounded(d,(48,458,912,984));text(d,(76,485),'АКТИВНІСТЬ ПО ДНЯХ',23,WHITE,True)
    for i,(dd,s) in enumerate(items):
        y=548+i*59
        text(d,(78,y-4),f'{dd:%d.%m}',22,WHITE)
        d.rounded_rectangle((198,y,749,y+24),radius=9,fill=GREY)
        frac=s['observed']/s['total'] if s['total'] else 0
        if frac>0:d.rounded_rectangle((198,y,198+max(8,int(551*frac)),y+24),radius=9,fill=GREEN)
        text(d,(882,y-4),f'{frac*100:.0f}%',22,GREEN if frac>=.5 else AMBER,anchor='ra')
    footer(d,1100);return png(im)

def render_month():
    now=utc_now().astimezone(TZ);day=now.date();first=day.replace(day=1)
    im,d=base('Поточний місяць',f'{day:%m.%Y}  ·  щоденна частка спостереження',1090)
    start,_=local_bounds(first)
    stat_cards(d,summary(start,utc_now()))
    rounded(d,(48,458,912,974));text(d,(75,485),'КАЛЕНДАР АКТИВНОСТІ',22,WHITE,True)
    import calendar
    offset=first.weekday();days=calendar.monthrange(day.year,day.month)[1];cell=93
    for i,name in enumerate(['ПН','ВТ','СР','ЧТ','ПТ','СБ','НД']): text(d,(114+i*116,540),name,20,MUTED,True,anchor='mt')
    for date_num in range(1,days+1):
        idx=offset+date_num-1;col=idx%7;row=idx//7
        x=74+col*116;y=570+row*66
        dd=first.replace(day=date_num)
        if dd>day:color=GREY
        else:
            s=daily(dd);q=s['observed']/s['total'] if s['total'] else 0
            color=GREEN if q>=.80 else '#8b824d' if q>.25 else '#704546'
        d.rounded_rectangle((x,y,x+80,y+53),radius=12,fill=color)
        text(d,(x+40,y+26),str(date_num),22,WHITE,True,anchor='mm')
    footer(d,1090);return png(im)

def render_history():
    im,d=base('Історія розривів','Останні періоди без heartbeat',1090)
    rounded(d,(48,220,912,968))
    gaps=recent_gaps(11)
    text(d,(78,247),'ПОЧАТОК',21,MUTED,True);text(d,(882,247),'ТРИВАЛІСТЬ',21,MUTED,True,anchor='ra')
    if not gaps:text(d,(78,322),'Розривів поки немає',29,WHITE)
    for i,g in enumerate(gaps):
        y=308+i*57
        if i: d.line((78,y-12,880,y-12),fill=EDGE,width=2)
        try: when=datetime.fromisoformat(g['started_at']).astimezone(TZ).strftime('%d.%m.%Y  %H:%M')
        except Exception: when='—'
        text(d,(78,y),when,23,WHITE)
        text(d,(882,y),format_duration(g['seconds']),23,RED,anchor='ra')
    footer(d,1090);return png(im)

def png(im):
    out=io.BytesIO();im.save(out,format='PNG',optimize=True);return out.getvalue()

RENDERERS={'today':render_today,'week':render_week,'month':render_month,'history':render_history}

def render(section): return RENDERERS.get(section,render_today)()
