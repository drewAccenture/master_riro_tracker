"""US-11 joiner page (plan slice 5, section 3.1): the deadline ladder and the banner meter from core/overview.py.

Pure: roll-on and "Status as of" dates are passed in. Synthetic tasks only.
"""

from datetime import date

import pytest
from joiner_fakes import SIX_TASKS

from riro.core.models import Task, TaskStatus
from riro.core.overview import Ladder, LadderColumn, MeterSegment, ladder, meter
from riro.core.status import compute

ROLL_ON = date(2026, 11, 2)


def t(index, deadline):
    return Task(
        index + 2,
        str(index + 1),
        "PMO",
        f"Invented task {index + 1}",
        deadline,
        "Not Started",
        None,
    )


# (deadline text, track) per task index. Offsets: -10, 0 and 1, plus two unclear deadlines.
ROWS = [
    ("On Roll On", "Completed"),  # 0
    ("10 days Before Roll On", "Delayed"),  # 1
    ("On Roll On", "Delayed"),  # 2
    ("1 days After Roll On", "On Track"),  # 3
    ("whenever it suits", "Deadline unclear"),  # 4
    ("0 days After Roll On", "N/A"),  # 5, same offset as "On Roll On"
    ("On Roll On", "Completed Late"),  # 6
    ("On Roll On", "On Track"),  # 7
    ("ask the invented manager", "Completed"),  # 8, unclear deadline but Completed
    ("on roll-on", "Delayed"),  # 9
]
TASKS = [t(i, deadline) for i, (deadline, _) in enumerate(ROWS)]
STATUSES = [TaskStatus(track, None, None) for _, track in ROWS]


def test_us11_one_column_per_distinct_offset_ascending_and_one_unclear_column_last():
    result = ladder(TASKS, STATUSES, ROLL_ON, date(2026, 11, 5))
    assert isinstance(result, Ladder)
    assert result.columns == (
        LadderColumn(-10, date(2026, 10, 23), ((1, "Delayed"),)),
        LadderColumn(
            0,
            date(2026, 11, 2),
            (
                (2, "Delayed"),
                (9, "Delayed"),
                (7, "On Track"),
                (0, "Completed"),
                (6, "Completed Late"),
                (5, "N/A"),
            ),
        ),
        LadderColumn(1, date(2026, 11, 3), ((3, "On Track"),)),
        LadderColumn(None, None, ((8, "Completed"), (4, "Deadline unclear"))),
    )


def test_us11_no_unclear_column_when_every_deadline_is_readable():
    tasks, statuses = TASKS[:4], STATUSES[:4]
    result = ladder(tasks, statuses, ROLL_ON, date(2026, 11, 5))
    assert [c.offset for c in result.columns] == [-10, 0, 1]


def test_us11_only_unclear_deadlines_give_one_unclear_column():
    tasks, statuses = [TASKS[4], TASKS[8]], [STATUSES[4], STATUSES[8]]
    result = ladder(tasks, statuses, ROLL_ON, date(2026, 11, 5))
    assert result.columns == (
        LadderColumn(None, None, ((1, "Completed"), (0, "Deadline unclear"))),
    )
    assert result.marker_before == 0


def test_us11_no_tasks_gives_an_empty_ladder():
    assert ladder([], [], ROLL_ON, date(2026, 11, 5)) == Ladder((), 0)


@pytest.mark.parametrize(
    ("as_of", "marker_before"),
    [
        (date(2026, 10, 1), 0),  # before every column: at the start
        (date(2026, 10, 23), 0),  # equal to the first due date
        (date(2026, 10, 24), 1),  # middle
        (date(2026, 11, 2), 1),
        (date(2026, 11, 3), 2),
        (
            date(2026, 11, 4),
            3,
        ),  # after every dated column: at the end, before "Deadline unclear"
        (date(2027, 1, 1), 3),
    ],
)
def test_us11_marker_goes_before_the_first_column_due_on_or_after_as_of(
    as_of, marker_before
):
    assert ladder(TASKS, STATUSES, ROLL_ON, as_of).marker_before == marker_before


def test_us03_due_dates_follow_the_roll_on_date():
    later = ladder(TASKS, STATUSES, date(2026, 12, 1), date(2026, 11, 5))
    assert [c.due for c in later.columns] == [
        date(2026, 11, 21),
        date(2026, 12, 1),
        date(2026, 12, 2),
        None,
    ]
    assert later.marker_before == 0


# --- meter ---------------------------------------------------------------------------------------------------------


def _segments(status):
    return [(s.track, s.count) for s in meter(status)]


def test_us11_meter_order_and_percent_of_all_tasks_in_the_file():
    status = compute(SIX_TASKS, ROLL_ON, date(2026, 11, 5))
    segments = meter(status)
    assert all(isinstance(s, MeterSegment) for s in segments)
    assert _segments(status) == [
        ("Completed", 1),
        ("Completed Late", 1),
        ("On Track", 1),
        ("Delayed", 1),
    ]
    # Divided by the file's own 6 tasks (N/A and unclear count in the total), not by 96.
    assert [s.percent for s in segments] == pytest.approx([100 / 6] * 4)


def test_us11_meter_leaves_out_zero_count_segments():
    tasks = [
        Task(2, "1", "PMO", "Invented task 1", "On Roll On", "Completed", ROLL_ON),
        Task(3, "2", "PMO", "Invented task 2", "On Roll On", "Completed", ROLL_ON),
        Task(4, "3", "PMO", "Invented task 3", "On Roll On", "Not Started", None),
        Task(5, "4", "PMO", "Invented task 4", "On Roll On", "Not Applicable", None),
    ]
    segments = meter(compute(tasks, ROLL_ON, date(2026, 11, 5)))
    assert [(s.track, s.count) for s in segments] == [("Completed", 2), ("Delayed", 1)]
    assert [s.percent for s in segments] == pytest.approx([50.0, 25.0])


def test_us11_meter_of_a_file_with_no_tasks_is_empty():
    assert meter(compute((), ROLL_ON, date(2026, 11, 5))) == ()


def test_us05_meter_follows_each_joiners_own_statuses():
    early = compute(SIX_TASKS, ROLL_ON, date(2026, 11, 5))
    late = compute(SIX_TASKS, date(2026, 11, 9), date(2026, 11, 5))
    assert _segments(early) != _segments(late)
    assert _segments(late) == [("Completed", 2), ("On Track", 2)]
