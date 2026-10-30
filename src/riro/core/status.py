"""Status of each task and joiner (US-04). The only place these rules live; same rules as the original HTML."""

from collections.abc import Sequence
from datetime import date, timedelta

from riro.core.deadlines import day_offset
from riro.core.models import JoinerStatus, Task, TaskStatus

DELAYED, ON_TRACK, COMPLETED, COMPLETED_LATE, NA, UNCLEAR = TRACKS = (
    "Delayed",
    "On Track",
    "Completed",
    "Completed Late",
    "N/A",
    "Deadline unclear",
)


def task_status(task: Task, roll_on: date, as_of: date) -> TaskStatus:
    offset = day_offset(task.deadline)
    due = None if offset is None else roll_on + timedelta(days=offset)
    if task.status == "Not Applicable":
        return TaskStatus(NA, due, None)
    if task.status == "Completed":
        done_on = task.completion_date
        if due is not None and done_on is not None and done_on > due:
            return TaskStatus(COMPLETED_LATE, due, (due - done_on).days)
        return TaskStatus(COMPLETED, due, None)
    if due is None:
        return TaskStatus(UNCLEAR, None, None)
    days = (due - as_of).days
    return TaskStatus(DELAYED if days < 0 else ON_TRACK, due, days)


def compute(tasks: Sequence[Task], roll_on: date, as_of: date) -> JoinerStatus:
    statuses = tuple(task_status(task, roll_on, as_of) for task in tasks)
    counts = dict.fromkeys(TRACKS, 0)
    for status in statuses:
        counts[status.track] += 1
    applicable = len(statuses) - counts[NA]
    done = counts[COMPLETED] + counts[COMPLETED_LATE]
    # Integer round half up, like the HTML's Math.round (Python's round() rounds half to even).
    percent = (done * 200 + applicable) // (2 * applicable) if applicable else 0
    # Every unreadable Deadline warns, also on Completed and N/A tasks (US-04).
    unclear = sum(1 for task in tasks if day_offset(task.deadline) is None)
    warnings = ()
    if unclear:
        verb = "task has" if unclear == 1 else "tasks have"
        warnings = (f"{unclear} {verb} a deadline the app cannot read",)
    return JoinerStatus(
        tasks=statuses,
        counts=counts,
        applicable=applicable,
        done=done,
        percent=percent,
        delayed=counts[DELAYED] > 0,
        delayed_count=counts[DELAYED],
        warnings=warnings,
    )
