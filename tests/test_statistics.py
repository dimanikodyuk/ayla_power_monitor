import unittest
from app.statistics import format_duration,local_bounds
from datetime import date
class TestStats(unittest.TestCase):
    def test_duration(self): self.assertEqual(format_duration(3660),"1 год 1 хв")
    def test_day(self):
        a,b=local_bounds(date(2026,11,18))
        self.assertEqual(int((b-a).total_seconds()),86400)
if __name__=="__main__":unittest.main()
