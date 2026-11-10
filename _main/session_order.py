"""Chronological ordering for GoNoGo batch outputs."""
from datetime import datetime, timezone


def session_start_time(session):
    value = session.get("session_start_time")
    return value.isoformat() if isinstance(value, datetime) else value


def session_sort_key(item):
    key, result = item
    try:
        value = result.get("session_start_time")
        if not isinstance(value, datetime):
            value = datetime.fromisoformat(value or "")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Missing timezone")
        return (0, value.astimezone(timezone.utc).timestamp(), str(key))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return (1, 0, str(key))


def ordered_sessions(results):
    return dict(sorted(results.items(), key=session_sort_key))
