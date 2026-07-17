from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

# Israeli license plates contain only digits: 7 (pre-2017) or 8 (2017+).
PLATE_MIN_DIGITS = 7
PLATE_MAX_DIGITS = 8

# A run of digits optionally separated by dash-like characters, matching how
# plates are printed (e.g. "12-345-67", "123-45-678").
_PLATE_TOKEN_PATTERN = re.compile(r"\d(?:[-–—.·]?\d)+")


def is_valid_plate_number(digits: str) -> bool:
    return digits.isdigit() and PLATE_MIN_DIGITS <= len(digits) <= PLATE_MAX_DIGITS


def extract_plate_from_ocr_text(raw_text: str) -> str:
    """Extract a plausible Israeli plate (7-8 digits) from OCR text.

    Unlike naive digit concatenation, this refuses to merge digits from
    unrelated text (permit stickers, phone numbers), so a legitimate plate is
    never corrupted by surrounding noise. Returns "" when no candidate looks
    like a real plate, which routes the event to manual admin review.
    """
    if not raw_text:
        return ""

    # Pass 1: contiguous digit tokens, dashes/dots allowed ("123-45-678").
    for match in _PLATE_TOKEN_PATTERN.finditer(raw_text):
        digits = "".join(ch for ch in match.group() if ch.isdigit())
        if is_valid_plate_number(digits):
            return digits

    # Pass 2: OCR sometimes renders plate separators as spaces; join digits
    # within a single line only (never across lines). Tokens that mix letters
    # with digits (e.g. the plate's blue "IL" country band misread as "1L")
    # are OCR noise, never plate digits, so they are dropped before joining.
    for line in raw_text.splitlines():
        tokens = []
        for token in line.split():
            if any(ch.isalpha() for ch in token):
                continue
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits:
                tokens.append(digits)
        if not tokens:
            continue

        # The "IL" band is also sometimes OCR'd as a standalone "1" to the
        # left of the plate. A real 8-digit plate is printed 123-45-678 and
        # never splits as "1 2345678", so when the groups after a lone
        # leading "1" already form a valid plate, the "1" is the band.
        remainder = "".join(tokens[1:])
        if tokens[0] == "1" and is_valid_plate_number(remainder):
            return remainder

        joined = "".join(tokens)
        if is_valid_plate_number(joined):
            return joined

    return ""


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
