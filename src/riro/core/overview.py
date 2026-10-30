"""Numbers for the overview and joiner screens (US-11), same rules as the original HTML. Pure: as_of is passed in.

Only joiners with a roll-on date are passed in; the caller leaves out waiting and hidden joiners (US-03, US-10).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from riro.core.deadlines import day_offset
from riro.core.models import JoinerStatus, Task, TaskStatus
from riro.core.status import TRACKS

BUCKETS = ("overdue", "today", "soon", "week", "later")
_OPEN = ("Delayed", "On Track")
_METER_ORDER = ("Completed", "Completed Late", "On Track", "Delayed")


def is_open(track: str) -> bool:
    """Open = not done and not N/A, with a readable deadline: the only tasks that are bucketed."""
    return track in _OPEN


def bucket_of(days: int) -> str:
    if days < 0:
        return "overdue"
    if days == 0:
        return "today"
    if days <= 3:
        return "soon"
    if days <= 7:
        return "week"
    return "later"


def _round_half_up(numerator: int, denominator: int) -> int:
    """round(numerator / denominator) with .5 going up, like the HTML's Math.round (Python rounds half to even)."""
    return (2 * numerator + denominator) // (2 * denominator)


@dataclass(frozen=True)
class OverviewJoiner:
    id: str
    name: str
    roll_on: date
    status: JoinerStatus
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class HeatRow:
    id: str
    name: str
    roll_on: date
    buckets: dict[str, int]
    percent: int
    since: int  # days from roll-on to as-of; negative before the roll-on


@dataclass(frozen=True)
class AttentionItem:
    joiner_id: str
    joiner_name: str
    task_index: int
    task: Task
    days: int


@dataclass(frozen=True)
class Overview:
    joiners: int
    delayed: int
    due_soon: int  # open tasks due within 3 days (0..3), overdue not included
    average: int  # mean of each joiner's percent, rounded half up
    rows: tuple[HeatRow, ...]
    attention: tuple[
        AttentionItem, ...
    ]  # open tasks due today or overdue, most overdue first


def overview(joiners: Sequence[OverviewJoiner], as_of: date) -> Overview:
    rows, attention = [], []
    due_soon = 0
    for joiner in joiners:
        buckets = dict.fromkeys(BUCKETS, 0)
        for index, status in enumerate(joiner.status.tasks):
            if not is_open(status.track):
                continue
            buckets[bucket_of(status.days)] += 1
            due_soon += 0 <= status.days <= 3
            if status.days <= 0:
                attention.append(
                    AttentionItem(
                        joiner.id, joiner.name, index, joiner.tasks[index], status.days
                    )
                )
        rows.append(
            HeatRow(
                id=joiner.id,
                name=joiner.name,
                roll_on=joiner.roll_on,
                buckets=buckets,
                percent=joiner.status.percent,
                since=(as_of - joiner.roll_on).days,
            )
        )
    total = sum(j.status.percent for j in joiners)
    return Overview(
        joiners=len(joiners),
        delayed=sum(j.status.counts["Delayed"] for j in joiners),
        due_soon=due_soon,
        average=_round_half_up(total, len(joiners)) if joiners else 0,
        rows=tuple(rows),
        attention=tuple(
            sorted(attention, key=lambda item: item.days)
        ),  # stable: ties keep joiner, task order
    )


@dataclass(frozen=True)
class LadderColumn:
    offset: int | None  # None = the "deadline unclear" column
    due: date | None
    squares: tuple[tuple[int, str], ...]  # (task index, track)


@dataclass(frozen=True)
class Ladder:
    columns: tuple[LadderColumn, ...]
    marker_before: int  # the "Status as of" line goes before this column


def ladder(
    tasks: Sequence[Task], statuses: Sequence[TaskStatus], roll_on: date, as_of: date
) -> Ladder:
    by_offset: dict[int | None, list[tuple[int, str]]] = {}
    for index, (task, status) in enumerate(zip(tasks, statuses, strict=True)):
        by_offset.setdefault(day_offset(task.deadline), []).append(
            (index, status.track)
        )
    order = {track: rank for rank, track in enumerate(TRACKS)}
    columns = []
    for offset in sorted(o for o in by_offset if o is not None):
        squares = sorted(by_offset[offset], key=lambda sq: (order[sq[1]], sq[0]))
        columns.append(
            LadderColumn(offset, roll_on + timedelta(days=offset), tuple(squares))
        )
    dated = len(columns)
    marker = next((i for i, c in enumerate(columns) if c.due >= as_of), dated)
    if None in by_offset:
        squares = sorted(by_offset[None], key=lambda sq: (order[sq[1]], sq[0]))
        columns.append(LadderColumn(None, None, tuple(squares)))
    return Ladder(columns=tuple(columns), marker_before=marker)


@dataclass(frozen=True)
class MeterSegment:
    track: str
    count: int
    percent: float


def meter(status: JoinerStatus) -> tuple[MeterSegment, ...]:
    """Segment widths over the file's own task count (the original divided by its fixed 96)."""
    total = len(status.tasks)
    if not total:
        return ()
    return tuple(
        MeterSegment(track, status.counts[track], status.counts[track] / total * 100)
        for track in _METER_ORDER
        if status.counts[track]
    )
