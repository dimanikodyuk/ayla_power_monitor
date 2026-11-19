"""Local host diagnostics. Does not assert mains electricity status."""
from __future__ import annotations
import os
import platform
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from .config import DB_PATH, INTERVAL, TZ
from .database import connect, utc_now


def snapshot():
    now = utc_now()
    with connect() as db:
        state = db.execute('SELECT * FROM state WHERE id=1').fetchone()
        sessions = db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
        gaps = db.execute('SELECT COUNT(*) FROM gaps').fetchone()[0]
        try:
            sqlite_ok = db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        except sqlite3.Error:
            sqlite_ok = False
    last = datetime.fromisoformat(state['last_seen']) if state else None
    age = max(0.0, (now - last).total_seconds()) if last else None
    is_linux = platform.system() == 'Linux'
    # Windows mode is for dashboard development, not power monitoring.
    active = bool(is_linux and age is not None and age <= max(45, INTERVAL * 3))
    boot_seconds = None
    if is_linux:
        try:
            with open('/proc/uptime', encoding='utf-8') as f:
                boot_seconds = float(f.read().split()[0])
        except OSError:
            pass
    sync = 'Невідомо'
    if is_linux:
        try:
            p = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                               capture_output=True, text=True, timeout=3)
            sync = 'Так' if p.returncode == 0 and p.stdout.strip() == 'yes' else 'Ні'
        except (OSError, subprocess.TimeoutExpired):
            pass
    disk = shutil.disk_usage(DB_PATH.parent)
    return {
        'system': platform.system(), 'active': active, 'last': last,
        'age': age, 'uptime': boot_seconds, 'ntp': sync,
        'db_ok': sqlite_ok, 'db_bytes': DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        'disk_free_gb': disk.free / 1024**3, 'sessions': sessions,
        'gaps': gaps, 'interval': INTERVAL,
        'sampled_at': now.astimezone(TZ),
    }
