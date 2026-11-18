from datetime import datetime, timedelta, timezone
from .config import TZ, INTERVAL
from .database import connect, utc_now

def local_bounds(day):
    start=datetime.combine(day, datetime.min.time(), TZ)
    end=start+timedelta(days=1)
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc)

def get_gaps(start,end):
    with connect() as db:
        rows=db.execute("SELECT * FROM gaps WHERE started_at < ? AND ended_at > ? ORDER BY started_at",
                        (end.isoformat(),start.isoformat())).fetchall()
    return [dict(r) for r in rows]

def summary(start,end):
    now=utc_now()
    end=min(end,now)
    if end<=start:
        return {"total":0,"observed":0,"unknown":0,"gaps":[]}
    with connect() as db:
        state=db.execute("SELECT last_seen FROM state WHERE id=1").fetchone()
        first=db.execute("SELECT MIN(started_at) AS first FROM sessions").fetchone()["first"]
    if not first:
        return {"total":(end-start).total_seconds(),"observed":0,"unknown":(end-start).total_seconds(),"gaps":[]}
    first=datetime.fromisoformat(first)
    active_start=max(start,first)
    intervals=[]
    for g in get_gaps(start,end):
        a=max(start,datetime.fromisoformat(g["started_at"]))
        b=min(end,datetime.fromisoformat(g["ended_at"]))
        if b>a:
            intervals.append((a,b,g))
    if first>start:
        intervals.append((start,min(first,end),{"kind":"unknown","note":"Before monitoring started"}))
    # If heartbeat is stale, the unobserved tail must not count as observed.
    if state:
        last=datetime.fromisoformat(state["last_seen"])
        stale_from=last+timedelta(seconds=INTERVAL*2)
        if stale_from<end:
            intervals.append((max(start,stale_from),end,{"kind":"unknown","note":"No recent heartbeat"}))
    intervals.sort(key=lambda x:x[0])
    merged=[]
    for a,b,g in intervals:
        if merged and a<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:
            merged.append((a,b))
    unknown=sum((b-a).total_seconds() for a,b in merged)
    total=(end-start).total_seconds()
    return {"total":total,"observed":max(0,total-unknown),
            "unknown":unknown,"gaps":get_gaps(start,end)}

def format_duration(seconds):
    minutes=round(seconds/60)
    h,m=divmod(minutes,60)
    return f"{h} год {m} хв"

def daily(day):
    return summary(*local_bounds(day))
