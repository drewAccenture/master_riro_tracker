"""US-04: status of one joiner from their tasks (plan slice 2, section 3.3, compute()).

Roll-on 2026-11-02, as-of 2026-11-10. Deadlines used below:
  "On Roll On" due 11-02 (open -> Delayed), "30 days After Roll On" due 12-02 (open -> On Track).
"""

import dataclasses
from datetime import date

import pytest

from riro.core.models import JoinerStatus, Task
from riro.core.status import TRACKS, compute, task_status

ROLL_ON = date(2026, 11, 2)
AS_OF = date(2026, 11, 10)
WARNING_TAIL = "deadline the app cannot read"


def _task(status, deadline="On Roll On", completion_date=None, n=1):
    return Task(
        row_number=n + 1,
        number=str(n),
        role="PMO",
        description=f"Invented task {n}",
        deadline=deadline,
        status=status,
        completion_date=completion_date,
    )


def done():
    return _task("Completed", completion_date=date(2026, 11, 1))


def late():
    return _task("Completed", completion_date=date(2026, 11, 5))


def delayed():
    return _task("Not Started")


def on_track():
    return _task("In Progress", "30 days After Roll On")


def na():
    return _task("Not Applicable")


def unclear():
    return _task("Not Started", "Never")


def _counts(**given):
    names = {
        "delayed": "Delayed",
        "on_track": "On Track",
        "completed": "Completed",
        "late": "Completed Late",
        "na": "N/A",
        "unclear": "Deadline unclear",
    }
    result = dict.fromkeys(TRACKS, 0)
    for key, value in given.items():
        result[names[key]] = value
    return result


def test_us04_compute_returns_frozen_joiner_status():
    result = compute([done()], ROLL_ON, AS_OF)
    assert isinstance(result, JoinerStatus)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.percent = 0


def test_us04_no_tasks_gives_zeros():
    result = compute([], ROLL_ON, AS_OF)
    assert result.tasks == ()
    assert result.counts == _counts()
    assert result.applicable == 0
    assert result.done == 0
    assert result.percent == 0
    assert result.delayed is False
    assert result.delayed_count == 0
    assert result.warnings == ()


def test_us04_counts_have_all_six_tracks_including_zeros():
    result = compute([done(), done()], ROLL_ON, AS_OF)
    assert set(result.counts) == set(TRACKS)
    assert result.counts == _counts(completed=2)


def test_us04_counts_one_of_each_track():
    tasks = [delayed(), on_track(), done(), late(), na(), unclear()]
    result = compute(tasks, ROLL_ON, AS_OF)
    assert result.counts == _counts(
        delayed=1, on_track=1, completed=1, late=1, na=1, unclear=1
    )
    assert result.applicable == 5
    assert result.done == 2
    assert result.percent == 40


def test_us04_tasks_are_one_status_per_task_in_order():
    tasks = [na(), late(), delayed(), done(), on_track()]
    result = compute(tasks, ROLL_ON, AS_OF)
    assert result.tasks == tuple(task_status(t, ROLL_ON, AS_OF) for t in tasks)
    assert [s.track for s in result.tasks] == [
        "N/A",
        "Completed Late",
        "Delayed",
        "Completed",
        "On Track",
    ]


def test_us04_compute_accepts_a_tuple_too():
    tasks = (done(), delayed())
    assert compute(tasks, ROLL_ON, AS_OF) == compute(list(tasks), ROLL_ON, AS_OF)


def test_us04_applicable_is_all_tasks_minus_na():
    result = compute([na(), na(), done(), delayed()], ROLL_ON, AS_OF)
    assert result.applicable == 2
    assert result.done == 1
    assert result.percent == 50


def test_us04_done_counts_completed_and_completed_late():
    result = compute([done(), late(), late(), delayed()], ROLL_ON, AS_OF)
    assert result.done == 3
    assert result.applicable == 4
    assert result.percent == 75


@pytest.mark.parametrize(
    "n_done, n_open, percent",
    [
        (1, 7, 13),  # 12.5 rounds half up, not to even
        (3, 5, 38),  # 37.5
        (5, 3, 63),  # 62.5
        (7, 1, 88),  # 87.5
        (2, 1, 67),  # 66.67
        (1, 2, 33),  # 33.33
        (0, 4, 0),
        (4, 0, 100),
    ],
)
def test_us04_percent_rounds_half_up(n_done, n_open, percent):
    tasks = [done() for _ in range(n_done)] + [on_track() for _ in range(n_open)]
    result = compute(tasks, ROLL_ON, AS_OF)
    assert result.percent == percent
    assert type(result.percent) is int


def test_us04_all_na_gives_zero_percent():
    result = compute([na(), na(), na()], ROLL_ON, AS_OF)
    assert result.applicable == 0
    assert result.done == 0
    assert result.percent == 0
    assert result.counts == _counts(na=3)
    assert result.delayed is False


def test_us04_any_delayed_task_marks_joiner_delayed_with_count():
    result = compute([delayed(), done(), delayed(), on_track()], ROLL_ON, AS_OF)
    assert result.delayed is True
    assert result.delayed_count == 2
    assert result.counts["Delayed"] == 2


def test_us04_no_delayed_task_means_on_track_joiner():
    result = compute([done(), late(), on_track(), na()], ROLL_ON, AS_OF)
    assert result.delayed is False
    assert result.delayed_count == 0


def test_us04_unclear_deadline_is_neither_delayed_nor_on_track():
    result = compute([unclear(), unclear()], ROLL_ON, AS_OF)
    assert result.counts == _counts(unclear=2)
    assert result.delayed is False
    assert result.delayed_count == 0


def test_us04_unclear_deadline_tasks_stay_in_applicable():
    result = compute([done(), unclear()], ROLL_ON, AS_OF)
    assert result.applicable == 2
    assert result.done == 1
    assert result.percent == 50


def test_us04_warning_names_how_many_deadlines_are_unclear():
    result = compute([unclear(), done(), unclear()], ROLL_ON, AS_OF)
    assert result.warnings == ("2 tasks have a deadline the app cannot read",)


def test_us04_warning_for_one_unclear_deadline():
    result = compute([unclear(), delayed()], ROLL_ON, AS_OF)
    assert len(result.warnings) == 1
    assert "1 task" in result.warnings[0]
    assert WARNING_TAIL in result.warnings[0]


def test_us04_no_warning_when_every_deadline_is_readable():
    result = compute([done(), delayed(), on_track(), na()], ROLL_ON, AS_OF)
    assert result.warnings == ()


def test_us04_completed_or_na_with_unclear_deadline_still_warns():
    # US-04: any unreadable Deadline text warns, whatever the task's status (user decision 2026-10-29).
    tasks = [_task("Completed", "Never"), _task("Not Applicable", "Day 0"), unclear()]
    result = compute(tasks, ROLL_ON, AS_OF)
    assert result.counts == _counts(completed=1, na=1, unclear=1)
    assert result.warnings == ("3 tasks have a deadline the app cannot read",)
