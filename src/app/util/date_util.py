import calendar
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9)) # UTC+9


# KST 기준 하루 [시작, 다음날 시작)
def kst_day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=KST)
    return start, start + timedelta(days=1)


# 오늘 날짜 (KST)
def today_kst() -> date:
    return datetime.now(KST).date()


# day에서 months개월 뒤(음수면 앞) 같은 날 (그 달에 없는 날이면 말일로: 5/31 - 3개월 -> 2/28)
def add_months(day: date, months: int) -> date:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month_index + 1, min(day.day, calendar.monthrange(year, month_index + 1)[1]))


# "2026-11" -> (그 달 1일, 다음 달 1일)
def month_range(month: str) -> tuple[date, date]:
    first_day = date(*map(int, month.split("-")), 1)
    return first_day, add_months(first_day, 1)

# 지금 시각(KST)
def now_kst() -> datetime:
    return datetime.now(KST)

# day가 있는 주 [월요일, 다음 주 월요일) - 이번주 돌아보기
def week_range(day:date) -> tuple[date,date]:
    monday = day - timedelta(days = day.weekday())
    return monday, monday + timedelta(days=7)


