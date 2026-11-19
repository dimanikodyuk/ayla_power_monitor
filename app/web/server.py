"""Read-only dashboard; Telegram initData or configured browser access token required."""
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from ..config import BOT_TOKEN, ADMIN_IDS, TZ
from ..database import connect, utc_now
from ..statistics import daily, summary, local_bounds

LOG = logging.getLogger(__name__)
STATIC = Path(__file__).parent
HOST = os.getenv("WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("WEB_PORT", "8096"))
ACCESS_TOKEN = os.getenv("WEB_ACCESS_TOKEN", "")


def validate_init_data(raw):
    if not BOT_TOKEN or not raw:
        return False
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True))
        given = pairs.pop("hash", "")
        auth_date = int(pairs.get("auth_date", "0"))
        if abs(time.time() - auth_date) > 3600 or not given:
            return False
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(given, calculated):
            return False
        user = json.loads(pairs.get("user", "{}"))
        return int(user.get("id", 0)) in ADMIN_IDS
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


@web.middleware
async def secure(request, handler):
    if request.path == "/health":
        return await handler(request)
    token = request.headers.get("X-Access-Token", "")
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    is_local = request.remote in ("127.0.0.1", "::1")
    if ((ACCESS_TOKEN and token and secrets.compare_digest(ACCESS_TOKEN, token))
            or validate_init_data(init_data)
            or (is_local and not ACCESS_TOKEN and not init_data)):
        return await handler(request)
    # Serve the HTML shell, but never expose dashboard data without authorization.
    if request.path == "/":
        return await handler(request)
    raise web.HTTPUnauthorized(text="Telegram authorization or WEB_ACCESS_TOKEN required")


async def index(request):
    return web.FileResponse(STATIC / "index.html")


async def health(request):
    return web.json_response({"ok": True})


def iso(dt):
    return dt.isoformat()


def snapshot():
    now = utc_now()
    today = now.astimezone(TZ).date()
    from_day, to_day = local_bounds(today)
    today_stats = daily(today)
    with connect() as db:
        state = db.execute("SELECT last_seen,boot_id FROM state WHERE id=1").fetchone()
        gaps = db.execute("SELECT id,started_at,ended_at,seconds,kind,note FROM gaps ORDER BY id DESC LIMIT 100").fetchall()
    last_seen = datetime.fromisoformat(state["last_seen"]) if state else None
    age = (now-last_seen).total_seconds() if last_seen else None
    week = []
    for n in range(6, -1, -1):
        day = today - timedelta(days=n)
        s = daily(day)
        cells=[]
        for h in range(24):
            a=datetime(day.year,day.month,day.day,h,tzinfo=TZ).astimezone(timezone.utc)
            b=(datetime(day.year,day.month,day.day,h+1,tzinfo=TZ).astimezone(timezone.utc)
               if h<23 else local_bounds(day)[1])
            bucket=summary(a,b)
            cells.append({"observed":round(bucket["observed"]),"total":round(bucket["total"])})
        week.append({"date": day.isoformat(), "observed": round(s["observed"]), "unknown": round(s["unknown"]), "total": round(s["total"]), "hours": cells})
    # Hourly buckets use real timezone-aware boundaries (handles DST).
    hours = []
    for h in range(24):
        a = datetime(today.year, today.month, today.day, h, tzinfo=TZ).astimezone(timezone.utc)
        b = (datetime(today.year, today.month, today.day, h+1, tzinfo=TZ).astimezone(timezone.utc)
             if h < 23 else to_day)
        s = summary(a,b)
        hours.append({"hour": h, "observed": round(s["observed"]), "unknown": round(s["unknown"]), "total": round(s["total"])})
    return {
        "generated_at": iso(now), "timezone": "Europe/Kyiv", "platform_mode": "estimated",
        "online": age is not None and 0 <= age <= 40, "heartbeat_age": round(age) if age is not None else None,
        "last_seen": iso(last_seen) if last_seen else None,
        "today": {k: round(today_stats[k]) for k in ("total", "observed", "unknown")},
        "week": week, "hours": hours,
        "gaps": [{"id": g["id"], "start": g["started_at"], "end": g["ended_at"],
                  "seconds": round(g["seconds"]), "kind": g["kind"]} for g in gaps],
    }


async def api_snapshot(request):
    return web.json_response(snapshot(), headers={"Cache-Control": "no-store"})


def run_server():
    app = web.Application(middlewares=[secure])
    app.router.add_get("/", index)
    app.router.add_get("/api/snapshot", api_snapshot)
    app.router.add_get("/health", health)
    web.run_app(app, host=HOST, port=PORT, handle_signals=False, print=None)


def start_server():
    thread = threading.Thread(target=run_server, daemon=True, name="dashboard-web")
    thread.start()
    LOG.info("Dashboard: http://%s:%s", HOST, PORT)
    return thread
