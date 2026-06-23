from __future__ import annotations

from datetime import datetime
from typing import Iterable


def normalize_datetime_for_comparison(value, now: datetime):
    if not hasattr(value, "tzinfo"):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=now.tzinfo)

    return value.astimezone(now.tzinfo)


def seconds_since(value, now: datetime):
    comparable = normalize_datetime_for_comparison(value, now)
    if comparable is None:
        return None

    return (now - comparable).total_seconds()


def should_preserve_recent_active_log(*,
                                      entry_time,
                                      license_plate: str | None,
                                      spot_last_seen,
                                      now: datetime,
                                      preserve_window_seconds: int,
                                      non_preservable_plates: Iterable[str]) -> bool:
    age_seconds = seconds_since(entry_time, now)
    if age_seconds is None or age_seconds < -1 or age_seconds > preserve_window_seconds:
        return False

    if license_plate in set(non_preservable_plates):
        return False

    entry_time_comparable = normalize_datetime_for_comparison(entry_time, now)
    last_seen_comparable = normalize_datetime_for_comparison(spot_last_seen, now)
    if entry_time_comparable is None:
        return False

    if last_seen_comparable is not None and entry_time_comparable < last_seen_comparable:
        return False

    return True
