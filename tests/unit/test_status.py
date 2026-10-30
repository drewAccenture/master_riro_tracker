"""US-04: status of one task (plan slice 2, section 3.3). Dates are passed in; no clock.

Roll-on is Monday 2026-11-02 in every test, so "1 days After Roll On" is due 2026-11-03.
"""

import dataclasses
from datetime import date, timedelta

import pytest

from riro.core.models import Task, TaskStatus
from riro.core.status import TRACKS, task_status

ROLL_ON = date(2026, 11, 2)
UNCLEAR_TEXTS = ["Day 0", "", "Never"]


def _task(status, deadline="1 days After Roll On", completion_date=None, note=""):
    return Task(
        row_number=2,
        number="1",
        role="PMO",
        description="Invented task",
        deadline=deadline,
        status=status,
        completion_date=completion_date,
        note=note,
    )


def test_us04_tracks_constant_is_the_six_tracks_in_order():
    assert TRACKS == (
        "Delayed",
        "On Track",
        "Completed",
        "Completed Late",
        "N/A",
        "Deadline unclear",
    )


def test_us04_task_status_is_frozen():
    result = task_status(_task("Not Started"), ROLL_ON, ROLL_ON)
    assert isinstance(result, TaskStatus)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.track = "x"


@pytest.mark.parametrize(
    "deadline, offset",
    [("10 days Before Roll On", -10), ("On Roll On", 0), ("42 days After Roll On", 42)],
)
def test_us04_due_is_roll_on_plus_offset(deadline, offset):
    result = task_status(_task("In Progress", deadline), ROLL_ON, ROLL_ON)
    assert result.due == ROLL_ON + timedelta(days=offset)


# --- Not Applicable -----------------------------------------------------------------


def test_us04_not_applicable_is_na_with_due_and_no_days():
    as_of = date(2026, 12, 1)  # long after the due date: still N/A, never Delayed
    result = task_status(_task("Not Applicable"), ROLL_ON, as_of)
    assert result == TaskStatus(track="N/A", due=date(2026, 11, 3), days=None)


def test_us04_not_applicable_with_unclear_deadline_has_no_due():
    result = task_status(_task("Not Applicable", "Never"), ROLL_ON, ROLL_ON)
    assert result == TaskStatus(track="N/A", due=None, days=None)


# --- Completed ----------------------------------------------------------------------


def test_us04_completed_after_due_is_completed_late():
    task = _task("Completed", completion_date=date(2026, 11, 5))
    result = task_status(task, ROLL_ON, date(2026, 11, 20))
    assert result == TaskStatus(track="Completed Late", due=date(2026, 11, 3), days=-2)


def test_us04_completed_one_day_after_due_is_late_by_one():
    task = _task("Completed", completion_date=date(2026, 11, 4))
    result = task_status(task, ROLL_ON, ROLL_ON)
    assert result.track == "Completed Late"
    assert result.days == -1


def test_us04_completed_late_uses_completion_date_not_as_of():
    task = _task("Completed", completion_date=date(2026, 11, 13))
    early = task_status(task, ROLL_ON, date(2026, 10, 1))
    late = task_status(task, ROLL_ON, date(2027, 1, 1))
    assert early == late == TaskStatus("Completed Late", date(2026, 11, 3), -10)


def test_us04_completed_on_due_day_is_completed():
    task = _task("Completed", completion_date=date(2026, 11, 3))
    result = task_status(task, ROLL_ON, date(2026, 11, 20))
    assert result == TaskStatus(track="Completed", due=date(2026, 11, 3), days=None)


def test_us04_completed_before_due_is_completed():
    task = _task("Completed", "10 days After Roll On", date(2026, 10, 20))
    result = task_status(task, ROLL_ON, ROLL_ON)
    assert result == TaskStatus(track="Completed", due=date(2026, 11, 12), days=None)


def test_us04_completed_without_date_is_completed():
    result = task_status(_task("Completed"), ROLL_ON, date(2026, 12, 1))
    assert result == TaskStatus(track="Completed", due=date(2026, 11, 3), days=None)


def test_us04_completed_with_unclear_completion_date_is_completed():
    task = _task("Completed", note="completion date unclear")
    result = task_status(task, ROLL_ON, date(2026, 12, 1))
    assert result.track == "Completed"
    assert result.days is None


@pytest.mark.parametrize("deadline", UNCLEAR_TEXTS)
def test_us04_completed_with_unclear_deadline_is_completed(deadline):
    task = _task("Completed", deadline, date(2027, 6, 1))
    result = task_status(task, ROLL_ON, ROLL_ON)
    assert result == TaskStatus(track="Completed", due=None, days=None)


# --- Open tasks: Not Started and In Progress ------------------------------------------


@pytest.mark.parametrize("status", ["Not Started", "In Progress"])
def test_us04_open_task_due_before_as_of_is_delayed(status):
    result = task_status(_task(status), ROLL_ON, date(2026, 11, 6))
    assert result == TaskStatus(track="Delayed", due=date(2026, 11, 3), days=-3)


@pytest.mark.parametrize("status", ["Not Started", "In Progress"])
def test_us04_open_task_one_day_overdue_is_delayed(status):
    result = task_status(_task(status), ROLL_ON, date(2026, 11, 4))
    assert result.track == "Delayed"
    assert result.days == -1


@pytest.mark.parametrize("status", ["Not Started", "In Progress"])
def test_us04_open_task_due_on_as_of_is_on_track(status):
    result = task_status(_task(status), ROLL_ON, date(2026, 11, 3))
    assert result == TaskStatus(track="On Track", due=date(2026, 11, 3), days=0)


@pytest.mark.parametrize("status", ["Not Started", "In Progress"])
def test_us04_open_task_due_after_as_of_is_on_track(status):
    task = _task(status, "10 days Before Roll On")
    result = task_status(task, ROLL_ON, date(2026, 10, 20))
    assert result == TaskStatus(track="On Track", due=date(2026, 10, 23), days=3)


@pytest.mark.parametrize("status", ["Not Started", "In Progress"])
@pytest.mark.parametrize("deadline", UNCLEAR_TEXTS)
def test_us04_open_task_with_unclear_deadline_is_deadline_unclear(status, deadline):
    result = task_status(_task(status, deadline), ROLL_ON, date(2027, 1, 1))
    assert result == TaskStatus(track="Deadline unclear", due=None, days=None)


def test_us04_open_task_ignores_a_completion_date():
    # read() drops such dates, but a Task built by hand must still not turn Completed.
    task = _task("Not Started", completion_date=date(2026, 11, 1))
    result = task_status(task, ROLL_ON, date(2026, 11, 6))
    assert result.track == "Delayed"


@pytest.mark.parametrize(
    "status, completion_date, as_of",
    [
        ("Not Applicable", None, ROLL_ON),
        ("Completed", date(2026, 11, 9), ROLL_ON),
        ("Completed", None, ROLL_ON),
        ("Not Started", None, date(2026, 11, 9)),
        ("In Progress", None, ROLL_ON),
    ],
)
def test_us04_every_track_is_one_of_tracks(status, completion_date, as_of):
    result = task_status(_task(status, completion_date=completion_date), ROLL_ON, as_of)
    assert result.track in TRACKS
