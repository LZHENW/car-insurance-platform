"""报表服务单元测试：日 / 周 / 月时间桶。"""

from datetime import datetime

from app.services import reports


class TestGetTimeRange:
    def test_日粒度(self):
        start, end = reports.get_time_range("day", "2026-09-28")
        assert start == datetime(2026, 9, 28, 0, 0, 0)
        assert end == datetime(2026, 9, 28, 23, 59, 59)

    def test_周粒度_周一起算(self):
        start, end = reports.get_time_range("week", "2026-09-28")
        assert start == datetime(2026, 9, 28, 0, 0, 0)
        assert end == datetime(2026, 10, 4, 23, 59, 59)

    def test_周粒度_周中归一到周一(self):
        start, _ = reports.get_time_range("week", "2026-10-01")
        assert start == datetime(2026, 9, 28, 0, 0, 0)

    def test_月粒度(self):
        start, end = reports.get_time_range("month", "2026-09-15")
        assert start == datetime(2026, 9, 1, 0, 0, 0)
        assert end == datetime(2026, 9, 30, 23, 59, 59)

    def test_默认取今天(self):
        start, _ = reports.get_time_range("day")
        assert start.date() == datetime.today().date()