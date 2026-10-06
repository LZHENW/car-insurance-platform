"""报表服务：时间桶计算（日 / 周 / 月）。"""

from datetime import date, datetime, timedelta
from typing import Optional


def get_time_range(dimension: str, date_str: Optional[str] = None):
    """按 日 / 周 / 月 粒度计算 [start, end] 时间闭区间。"""
    if not date_str:
        base = date.today()
    else:
        base = datetime.strptime(date_str, "%Y-%m-%d").date()

    if dimension == "day":
        start = datetime.combine(base, datetime.min.time())
        end = start + timedelta(days=1) - timedelta(seconds=1)
    elif dimension == "month":
        start = datetime.combine(base.replace(day=1), datetime.min.time())
        nxt = (start + timedelta(days=32)).replace(day=1)
        end = nxt - timedelta(seconds=1)
    else:  # week：以周一为一周起点
        week_start = base - timedelta(days=base.weekday())
        start = datetime.combine(week_start, datetime.min.time())
        end = start + timedelta(days=7) - timedelta(seconds=1)

    return start, end