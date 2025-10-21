from calendar import monthrange
from datetime import date, timedelta


def get_date_5days_before_end_of_month(today=None):
    if today is None:
        today = date.today()

    year, month = today.year, today.month
    last_day = monthrange(year, month)[1]
    end_of_month = date(year, month, last_day)

    if (end_of_month - today).days < 5:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        last_day = monthrange(year, month)[1]
        end_of_month = date(year, month, last_day)

    return end_of_month - timedelta(days=5)
