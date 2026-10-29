"""Display text for the tracker page (US-11): dates, days-to-due, badges, banner and the small lines.

Pure wording: no clock, no data access. Screens (screens.py) puts it together.
"""

import re
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from riro.core.models import JoinerStatus, SkippedRow, Task

MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_TILES = ("Delayed", "On Track", "Completed", "Completed Late", "N/A")
_CELL_CSS = {"overdue": "hd", "today": "hw", "soon": "hw", "week": "ho", "later": "ho"}


def long_date(d: date | datetime | None) -> str:
    return "" if d is None else f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}"


def short_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def day_label(offset: int | None) -> str:
    if offset is None:
        return "Deadline unclear"
    return "Day 0" if offset == 0 else f"Day {offset:+d}"


def days_text(track: str, days: int | None) -> tuple[str, str]:
    if days is None:
        return "", ""
    if track == "Delayed":
        return f"{-days} overdue", "neg"
    if track == "On Track":
        if days == 0:
            return "Due today", "soon"
        return f"{days} left", "soon" if days <= 2 else ""
    if track == "Completed Late":
        return f"{-days} late", "neg"
    return "", ""


def attention_badge(days: int) -> tuple[str, str]:
    if days < 0:
        return plural(-days, "day late", "days late"), "Delayed"
    return "Today", "CompletedLate"


def banner(status: JoinerStatus) -> dict:
    done = (
        f" · {status.done} of {status.applicable} applicable tasks completed "
        f"({status.percent}%)"
    )
    if status.delayed_count:
        late = status.delayed_count
        verb = "task is" if late == 1 else "tasks are"
        return {
            "kind": "bad",
            "title": "Delayed",
            "text": f"{late} {verb} past deadline{done}",
        }
    return {
        "kind": "ok",
        "title": "On track",
        "text": f"No open task is past its deadline{done}",
    }


def _range(first: date, last: date) -> str:
    if (first.month, first.year) == (last.month, last.year):
        return f"{first.day}-{short_date(last)}"
    return f"{short_date(first)}-{short_date(last)}"


def bucket_columns(as_of: date) -> list[dict]:
    def day(n: int) -> date:
        return as_of + timedelta(days=n)

    return [
        {"key": "overdue", "label": "Overdue", "dates": f"before {short_date(as_of)}"},
        {"key": "today", "label": "Today", "dates": short_date(as_of)},
        {"key": "soon", "label": "1-3 days", "dates": _range(day(1), day(3))},
        {"key": "week", "label": "4-7 days", "dates": _range(day(4), day(7))},
        {"key": "later", "label": "Later", "dates": f"after {short_date(day(7))}"},
    ]


def task_title(description: str) -> str:
    return next((line.strip() for line in description.splitlines() if line.strip()), "")


def _is_team_member(role: str) -> bool:
    return " ".join(role.lower().split()) == "team member"


def owner(task: Task, joiner_name: str) -> str:
    return joiner_name if _is_team_member(task.role) else task.assigned_id


def skipped_text(rows: Sequence[SkippedRow]) -> str:
    if not rows:
        return ""
    reasons = "; ".join(dict.fromkeys(row.reason for row in rows))
    numbers = ", ".join(str(row.row_number) for row in rows)
    where = "row" if len(rows) == 1 else "rows"
    return f"{plural(len(rows), 'row', 'rows')} could not be read: {reasons} ({where} {numbers})."


def problem_text(problem: str | None, read_at: datetime | None) -> str:
    if problem is None:
        return ""
    if read_at is None:
        return f"File could not be read: {problem}."
    return f"File could not be read: {problem}, showing data from {long_date(read_at)}"


def since_text(since: int) -> str:
    return f"day {since}" if since >= 0 else plural(-since, "day to go", "days to go")


def css_name(track: str) -> str:
    return re.sub(r"[^A-Za-z]", "", track)


def ladder_key(offset: int | None) -> str:
    return "unclear" if offset is None else f"d{offset}"


def who_line(task: Task, joiner_name: str) -> str:
    if _is_team_member(task.role):
        return f"{joiner_name} · Team Member"
    if task.assigned_id:
        return f"{joiner_name} · {task.assigned_id}, {task.role}"
    return f"{joiner_name} · {task.role}"
