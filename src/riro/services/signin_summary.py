"""The "Sign-in summary" of the diagnostic report: visible sign-ins and silent renewals per day (US-08, US-16).

Pure: counts our own event lines ("YYYY-MM-DD HH:MM:SS step k=v ..."). Any other line is ignored.
"""

import re
from collections.abc import Iterable
from datetime import date, timedelta

TITLE = "Sign-in summary (last 7 days):"
DAYS = 7
_LINE = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} (\w+)((?: \w+=\S+)*)")


def seconds(value: float) -> str:
    """Same format as duration_s in the report: 12.4, 3, 0."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def summary_lines(lines: Iterable[str], today: date) -> list[str]:
    first = today - timedelta(days=DAYS - 1)
    days: dict[date, dict] = {}
    # One failed visible sign-in writes two lines: the connector's (with duration_s), then the service's (without).
    after_connector_failure = False
    for line in lines:
        found = _LINE.fullmatch(line.rstrip("\r\n"))
        if not found or found.group(2) not in ("sign_in", "renewal"):
            continue
        fields = dict(part.split("=", 1) for part in found.group(3).split())
        if found.group(2) == "sign_in":
            same_attempt = after_connector_failure and "duration_s" not in fields
            after_connector_failure = (
                "duration_s" in fields and fields.get("result") == "failed"
            )
            if same_attempt:
                continue
        day = _day(found.group(1))
        if day is None or not first <= day <= today:
            continue
        counts = days.setdefault(
            day, {"sign_in": [0, 0], "renewal": [0, 0], "longest": None}
        )
        step = counts[found.group(2)]
        step[0] += 1
        step[1] += fields.get("result") == "failed"
        if found.group(2) == "renewal" and "duration_s" in fields:
            try:
                duration = float(fields["duration_s"])
            except ValueError:
                continue
            if counts["longest"] is None or duration > counts["longest"]:
                counts["longest"] = duration
    out = []
    for day in sorted(days, reverse=True):
        c = days[day]
        text = (
            f"{day.isoformat()}: visible sign-ins {c['sign_in'][0]} (failed {c['sign_in'][1]}), "
            f"silent renewals {c['renewal'][0]} (failed {c['renewal'][1]})"
        )
        if c["longest"] is not None:
            text += f", longest renewal {seconds(c['longest'])} s"
        out.append(text)
    return out
