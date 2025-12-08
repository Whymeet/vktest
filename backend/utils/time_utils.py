from datetime import datetime, timedelta, timezone

# Moscow timezone (UTC+3)
MOSCOW_OFFSET = timedelta(hours=3)
MOSCOW_TZ = timezone(MOSCOW_OFFSET)

def get_moscow_time():
    """
    Returns current time in Moscow timezone (UTC+3) as naive datetime.
    Useful for databases that store naive datetimes but we want the value to be local time.
    """
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)

def get_moscow_time_aware():
    """
    Returns current time in Moscow timezone (UTC+3) as timezone-aware datetime.
    """
    return datetime.now(MOSCOW_TZ)
