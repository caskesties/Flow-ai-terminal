"""Push delivery windows in California local time; analysis runs continuously."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def within_session(now=None):
    local = (now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    clock = local.time()
    if local.weekday() == 6:
        return time(17) <= clock < time(20)
    if local.weekday() == 5:
        return False
    return time(6, 29) <= clock < time(8, 30) or time(16, 30) <= clock < time(20)


def event_in_session(timestamp_ms):
    return within_session(datetime.fromtimestamp(timestamp_ms / 1000, PACIFIC))
