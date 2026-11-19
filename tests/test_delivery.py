"""Offline Telegram stubs validate idempotent delivery and SQLite flags."""
import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from app import database

# Allow testing async delivery without installing Telegram/network access.
telegram=types.ModuleType('telegram')
for name in ('BotCommand','InlineKeyboardButton','InlineKeyboardMarkup','InputMediaPhoto'):
    setattr(telegram,name,type(name,(),{'__init__':lambda self,*a,**kw:None}))
class InputFile:
    def __init__(self,*a,**kw):pass
telegram.InputFile=InputFile
errors=types.ModuleType('telegram.error')
errors.BadRequest=type('BadRequest',(Exception,),{})
errors.TelegramError=type('TelegramError',(Exception,),{})
ext=types.ModuleType('telegram.ext')
for name in ('Application','CallbackQueryHandler','CommandHandler'):
    setattr(ext,name,type(name,(),{}))

class FakeBot:
    def __init__(self):self.messages=[];self.photos=[];self.fail=False
    async def send_message(self,**kwargs):
        if self.fail:raise errors.TelegramError('offline')
        self.messages.append(kwargs)
    async def send_photo(self,**kwargs):
        if self.fail:raise errors.TelegramError('offline')
        self.photos.append(kwargs)

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.mods=patch.dict(sys.modules,{'telegram':telegram,'telegram.error':errors,'telegram.ext':ext})
        self.mods.start()
        sys.modules.pop('app.telegram_bot',None)
        self.bot=importlib.import_module('app.telegram_bot')
        self.temp=tempfile.TemporaryDirectory()
        self.dbpatch=patch.object(database,'DB_PATH',Path(self.temp.name)/'test.db')
        self.dbpatch.start();database.init()
        self.chatpatch=patch.object(self.bot,'CHAT_ID','123')
        self.chatpatch.start()
        self.fake=FakeBot();self.app=types.SimpleNamespace(bot=self.fake)

    def tearDown(self):
        self.chatpatch.stop();self.dbpatch.stop();self.temp.cleanup()
        self.mods.stop();sys.modules.pop('app.telegram_bot',None)

    def test_gap_once_and_retry(self):
        with database.connect() as db:
            db.execute('INSERT INTO gaps(started_at,ended_at,seconds,kind) VALUES(?,?,?,?)',
                       ('2026-11-18T00:00:00+00:00','2026-11-18T01:00:00+00:00',3600,'unknown'))
        self.fake.fail=True
        with self.assertRaises(errors.TelegramError):
            asyncio.run(self.bot._deliver_gaps(self.app))
        with database.connect() as db:
            self.assertEqual(db.execute('SELECT notified FROM gaps').fetchone()[0],0)
        self.fake.fail=False
        asyncio.run(self.bot._deliver_gaps(self.app))
        asyncio.run(self.bot._deliver_gaps(self.app))
        self.assertEqual(len(self.fake.messages),1)

    def test_daily_once(self):
        with patch.object(self.bot,'utc_now',return_value=datetime(2026,11,19,8,tzinfo=timezone.utc)):
            asyncio.run(self.bot._deliver_daily(self.app))
            asyncio.run(self.bot._deliver_daily(self.app))
        self.assertEqual(len(self.fake.photos),1)
        self.assertEqual(database.setting('daily_last_sent'),'2026-11-18')

if __name__=='__main__':unittest.main()
