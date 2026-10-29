"""US-03 totals, US-11 overview (plan slice 5, section 3.1): core/overview.py buckets, KPIs, heatmap rows, attention.

Pure: the "Status as of" date is passed in. Statuses are built by hand so each rule is tested on its own.
"""

from datetime import date

import pytest

from riro.core.models import JoinerStatus, Task, TaskStatus
from riro.core.overview import (
    BUCKETS,
    AttentionItem,
    HeatRow,
    OverviewJoiner,
    bucket_of,
    overview,
)
from riro.core.status import TRACKS

AS_OF = date(2026, 11, 5)


def ts(track, days=None):
    return TaskStatus(track, None, days)


def joiner_status(statuses, percent=0):
    counts = dict.fromkeys(TRACKS, 0)
    for status in statuses:
        counts[status.track] += 1
    return JoinerStatus(
        tasks=tuple(statuses),
        counts=counts,
        applicable=len(statuses) - counts["N/A"],
        done=counts["Completed"] + counts["Completed Late"],
        percent=percent,
        delayed=counts["Delayed"] > 0,
        delayed_count=counts["Delayed"],
        warnings=(),
    )


def tasks_for(n):
    return tuple(
        Task(
            i + 2,
            str(i + 1),
            "PMO",
            f"Invented task {i + 1}",
            "On Roll On",
            "Not Started",
            None,
        )
        for i in range(n)
    )


def oj(joiner_id, name, roll_on, statuses, percent=0):
    return OverviewJoiner(
        joiner_id,
        name,
        roll_on,
        joiner_status(statuses, percent),
        tasks_for(len(statuses)),
    )


ALPHA = oj(
    "j-a",
    "Alpha Example",
    date(2026, 11, 2),
    [
        ts("Delayed", -2),
        ts("On Track", 0),
        ts("On Track", 3),
        ts("On Track", 4),
        ts("On Track", 7),
        ts("On Track", 8),
        ts("Completed Late", -3),  # not open: never bucketed, never in attention
        ts("Completed"),
        ts("N/A"),
        ts("Deadline unclear"),
    ],
    percent=40,
)
BETA = oj(
    "j-b",
    "Beta Example",
    date(2026, 11, 9),
    [
        ts("Delayed", -5),
        ts("Delayed", -1),
        ts("On Track", 1),
        ts("On Track", 0),
        ts("Delayed", -1),
    ],
    percent=45,
)


def test_us11_buckets_are_the_five_heatmap_columns_in_order():
    assert BUCKETS == ("overdue", "today", "soon", "week", "later")


@pytest.mark.parametrize(
    ("days", "bucket"),
    [
        (-30, "overdue"),
        (-1, "overdue"),
        (0, "today"),
        (1, "soon"),
        (3, "soon"),
        (4, "week"),
        (7, "week"),
        (8, "later"),
        (120, "later"),
    ],
)
def test_us11_bucket_boundaries(days, bucket):
    assert bucket_of(days) == bucket


def test_us11_kpis_count_joiners_delayed_due_soon_and_average():
    result = overview([ALPHA, BETA], AS_OF)
    assert result.joiners == 2
    assert result.delayed == 4  # 1 + 3
    assert result.due_soon == 4  # Alpha days 0 and 3, Beta days 1 and 0
    assert result.average == 43  # mean of 40 and 45 = 42.5, half up


def test_us11_heatmap_rows_have_all_five_buckets_percent_and_since():
    result = overview([ALPHA, BETA], AS_OF)
    assert result.rows == (
        HeatRow(
            "j-a",
            "Alpha Example",
            date(2026, 11, 2),
            {"overdue": 1, "today": 1, "soon": 1, "week": 2, "later": 1},
            40,
            3,
        ),
        HeatRow(
            "j-b",
            "Beta Example",
            date(2026, 11, 9),
            {"overdue": 3, "today": 1, "soon": 1, "week": 0, "later": 0},
            45,
            -4,
        ),
    )


def test_us11_rows_keep_the_input_order():
    result = overview([BETA, ALPHA], AS_OF)
    assert [row.id for row in result.rows] == ["j-b", "j-a"]


def test_us05_two_joiners_with_different_statuses_give_different_rows():
    rows = overview([ALPHA, BETA], AS_OF).rows
    assert rows[0].buckets != rows[1].buckets
    assert rows[0].percent != rows[1].percent


def test_us11_attention_is_open_tasks_due_today_or_earlier_sorted_with_stable_ties():
    result = overview([ALPHA, BETA], AS_OF)
    got = [(a.joiner_id, a.task_index, a.days) for a in result.attention]
    assert got == [
        ("j-b", 0, -5),
        ("j-a", 0, -2),
        ("j-b", 1, -1),  # tie at -1: task order within the joiner
        ("j-b", 4, -1),
        ("j-a", 1, 0),  # tie at 0: joiner order first
        ("j-b", 3, 0),
    ]


def test_us11_attention_item_carries_the_joiner_name_and_the_task():
    first = overview([ALPHA, BETA], AS_OF).attention[0]
    assert first == AttentionItem("j-b", "Beta Example", 0, BETA.tasks[0], -5)


def test_us11_attention_ties_follow_input_joiner_order():
    result = overview([BETA, ALPHA], AS_OF)
    zeros = [(a.joiner_id, a.task_index) for a in result.attention if a.days == 0]
    assert zeros == [("j-b", 3), ("j-a", 1)]


def test_us04_completed_late_na_completed_and_unclear_are_never_open():
    only_closed = oj(
        "j-c",
        "Closed Example",
        date(2026, 11, 2),
        [ts("Completed Late", -3), ts("Completed"), ts("N/A"), ts("Deadline unclear")],
        percent=100,
    )
    result = overview([only_closed], AS_OF)
    assert result.rows[0].buckets == dict.fromkeys(BUCKETS, 0)
    assert (result.delayed, result.due_soon, result.attention) == (0, 0, ())


def test_us03_no_joiners_gives_zero_kpis_and_no_rows():
    result = overview([], AS_OF)
    assert (result.joiners, result.delayed, result.due_soon, result.average) == (
        0,
        0,
        0,
        0,
    )
    assert (result.rows, result.attention) == ((), ())


@pytest.mark.parametrize(
    ("percents", "average"),
    [
        ((40, 45), 43),
        ((50, 25), 38),
        ((2, 3), 3),  # 2.5 rounds up, not to even
        ((33, 34), 34),
        ((10, 11, 11), 11),
        ((100, 0), 50),
        ((0,), 0),
        ((100,), 100),
    ],
)
def test_us11_average_is_the_mean_percent_rounded_half_up(percents, average):
    joiners = [
        oj(f"j-{i}", f"Example {i}", date(2026, 11, 2), [ts("Completed")], percent=p)
        for i, p in enumerate(percents)
    ]
    assert overview(joiners, AS_OF).average == average


def test_us11_since_counts_days_from_roll_on_to_as_of():
    on_the_day = oj("j-d", "Day Example", AS_OF, [ts("On Track", 0)])
    result = overview([on_the_day, ALPHA, BETA], AS_OF)
    assert [row.since for row in result.rows] == [0, 3, -4]


def test_us11_overview_joiner_is_frozen():
    with pytest.raises(AttributeError):
        ALPHA.name = "Changed"
