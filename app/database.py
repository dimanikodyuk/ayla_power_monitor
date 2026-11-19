"""SQLite storage. Connection context closes descriptors after every operation."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH


def utc_now():
    return datetime.now(timezone.utc)


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(DB_PATH,timeout=30)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        with db:
            yield db
    finally:
        db.close()


def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY CHECK (id=1),
            last_seen TEXT NOT NULL,
            boot_id TEXT NOT NULL,
            mono REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boot_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            seconds REAL NOT NULL,
            kind TEXT NOT NULL DEFAULT 'unknown',
            note TEXT NOT NULL DEFAULT '',
            notified INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_gaps_start ON gaps(started_at);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')


def setting(key,default=''):
    with connect() as db:
        row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row['value'] if row else default


def set_setting(key,value):
    with connect() as db:
        db.execute('INSERT INTO settings(key,value) VALUES (?,?) '
                   'ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))
