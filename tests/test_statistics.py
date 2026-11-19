import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app import database
from app.statistics import coverage, day_timeline, format_duration, local_bounds

UTC=timezone.utc

class TestStats(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(format_duration(3660),'1 год 01 хв')
        self.assertEqual(format_duration(0),'0 год 00 хв')

    def test_dst_days_kyiv(self):
        self.assertEqual((local_bounds(date(2026,3,29))[1]-local_bounds(date(2026,3,29))[0]).total_seconds(),23*3600)
        self.assertEqual((local_bounds(date(2026,10,25))[1]-local_bounds(date(2026,10,25))[0]).total_seconds(),25*3600)

    def test_gap_is_unknown_and_future_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(database,'DB_PATH',Path(folder)/'test.db'):
                database.init()
                a=datetime(2026,11,18,8,tzinfo=UTC)
                b=a+timedelta(hours=2)
                with database.connect() as db:
                    db.execute('INSERT INTO sessions(boot_id,started_at,last_seen) VALUES(?,?,?)',('boot',a.isoformat(),b.isoformat()))
                    db.execute('INSERT INTO gaps(started_at,ended_at,seconds,kind,note) VALUES(?,?,?,?,?)',
                               ((a+timedelta(minutes=30)).isoformat(),(a+timedelta(hours=1)).isoformat(),1800,'unknown','test'))
                result=coverage(a,a+timedelta(hours=4),now=a+timedelta(hours=3))
                self.assertAlmostEqual(result['total'],3*3600)
                self.assertAlmostEqual(result['observed'],5410)
                self.assertAlmostEqual(result['unknown'],5390)

    def test_future_bins_not_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(database,'DB_PATH',Path(folder)/'test.db'):
                database.init()
                day=date(2026,11,19)
                start,_=local_bounds(day)
                bins=day_timeline(day,24,now=start+timedelta(hours=6))
                self.assertEqual(sum(x[1] for x in bins),6*3600)
                self.assertEqual(sum(x[2] for x in bins),18*3600)

if __name__=='__main__':unittest.main()
