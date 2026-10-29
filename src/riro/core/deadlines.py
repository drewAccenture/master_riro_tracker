"""Deadline text -> day offset from the roll-on date (US-04, requirements section 8 open question 2)."""

import re

_ROLL_ON = r"roll\s*-?\s*on"
_ON_ROLL_ON = re.compile(rf"on\s+{_ROLL_ON}", re.IGNORECASE)
_DAYS = re.compile(rf"(\d+)\s+days?\s+(before|after)\s+{_ROLL_ON}", re.IGNORECASE)


def day_offset(text: str | None) -> int | None:
    """Days from roll-on (negative = before). None means "deadline unclear"."""
    cleaned = (text or "").strip()
    if _ON_ROLL_ON.fullmatch(cleaned):
        return 0
    match = _DAYS.fullmatch(cleaned)
    if match is None:
        return None
    days = int(match.group(1))
    return -days if match.group(2).lower() == "before" else days
