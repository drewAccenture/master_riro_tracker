"""US-05 (core half), US-02, US-04: two synthetic files -> read() -> compute() (plan slice 2, section 6).

Each joiner's tile counts come from their own file, so two files with different statuses give different counts.
Roll-on 2026-11-02 (Monday), status as of 2026-11-10. Expected numbers are worked out by hand in the comments.
"""

from datetime import date, datetime

import pytest

from riro.core.checklist import read
from riro.core.status import TRACKS, compute

ROLL_ON = date(2026, 11, 2)
AS_OF = date(2026, 11, 10)
OWNER_A = "Test Person A"
OWNER_B = "Test Person B"


@pytest.fixture
def file_a(make_checklist, make_row):
    def row(*args, **kwargs):
        return make_row(*args, owner=OWNER_A, **kwargs)

    return make_checklist(
        [
            # due 11-02, done 11-01 -> Completed
            row(1, "Invented A1", "Completed", date(2026, 11, 1), "On Roll On"),
            # due 11-03, done 11-06 -> Completed Late
            row(
                2, "Invented A2", "Completed", date(2026, 11, 6), "1 days After Roll On"
            ),
            # due 11-05 < 11-10 -> Delayed
            row(3, "Invented A3", "Not Started", None, "3 days After Roll On"),
            # due 11-12 >= 11-10 -> On Track
            row(4, "Invented A4", "In Progress", None, "10 days After Roll On"),
            # N/A
            row(5, "Invented A5", "Not Applicable", None, "On Roll On"),
        ]
    )


@pytest.fixture
def file_b(make_checklist, make_row):
    def row(*args, **kwargs):
        return make_row(*args, owner=OWNER_B, **kwargs)

    blank = [None] * 9
    owner_only = [OWNER_B, "PMO", None, None, "Completed", None, "On Roll On", "", ""]
    return make_checklist(
        [
            # due 11-01, done 10-30 (date and time cell) -> Completed
            row(
                1,
                "Invented B1",
                "Completed",
                datetime(2026, 10, 30, 9, 15),
                "1 days Before Roll On",
            ),
            # due 11-02, done 11-02 as yyyy-mm-dd text -> Completed (on the due day)
            row(2, "Invented B2", "completed", "2026-11-02", "On Roll On"),
            # no completion date -> Completed
            row(3, "Invented B3", "Completed", None, "5 days After Roll On"),
            # due 11-17 -> On Track
            row(4, "Invented B4", "Not Started", None, "15 days After Roll On"),
            # unknown status "Done" -> Not Started; deadline "Never" -> Deadline unclear
            row(5, "Invented B5", "Done", None, "Never"),
            # N/A
            row(6, "Invented B6", "NOT APPLICABLE", None, "2 days After Roll On"),
            blank,  # ignored, no message
            owner_only,  # skipped: no task number or description
        ],
        sheet="ROLL-IN",
    )


def _expected(delayed, on_track, completed, late, na, unclear):
    return dict(
        zip(TRACKS, (delayed, on_track, completed, late, na, unclear), strict=True)
    )


def test_us05_joiner_a_counts_come_from_file_a(file_a):
    checklist = read(file_a)
    assert checklist.owner == OWNER_A
    assert checklist.skipped_rows == ()
    status = compute(checklist.tasks, ROLL_ON, AS_OF)
    assert status.counts == _expected(1, 1, 1, 1, 1, 0)
    assert status.applicable == 4
    assert status.done == 2
    assert status.percent == 50
    assert status.delayed is True
    assert status.delayed_count == 1
    assert status.warnings == ()
    assert [s.track for s in status.tasks] == [
        "Completed",
        "Completed Late",
        "Delayed",
        "On Track",
        "N/A",
    ]


def test_us05_joiner_b_counts_come_from_file_b(file_b):
    checklist = read(file_b)
    assert checklist.owner == OWNER_B
    assert checklist.sheet_name == "ROLL-IN"
    assert checklist.unknown_status_rows == 1
    assert [(r.row_number, r.reason) for r in checklist.skipped_rows] == [
        (9, "no task number or description")
    ]
    status = compute(checklist.tasks, ROLL_ON, AS_OF)
    assert status.counts == _expected(0, 1, 3, 0, 1, 1)
    assert status.applicable == 5
    assert status.done == 3
    assert status.percent == 60
    assert status.delayed is False
    assert status.delayed_count == 0
    assert len(status.warnings) == 1
    assert "1 task" in status.warnings[0]
    assert "deadline the app cannot read" in status.warnings[0]


def test_us05_two_joiners_show_different_counts_and_percent(file_a, file_b):
    a = compute(read(file_a).tasks, ROLL_ON, AS_OF)
    b = compute(read(file_b).tasks, ROLL_ON, AS_OF)
    assert a.counts != b.counts
    assert a.percent != b.percent
    assert a.delayed != b.delayed


def test_us04_changing_as_of_moves_open_task_from_on_track_to_delayed(file_a):
    tasks = read(file_a).tasks
    later = compute(tasks, ROLL_ON, date(2026, 11, 13))  # A4 due 11-12 is now overdue
    assert later.counts == _expected(2, 0, 1, 1, 1, 0)
    assert later.delayed_count == 2
    assert later.percent == 50
