"""US-05, US-09, US-11 (plan slice 5, section 3.2): display text built in services/screens.py, never in the page."""

from datetime import date, datetime

import pytest
from joiner_fakes import SIX_TASKS

from riro.core.models import SkippedRow, Task
from riro.core.status import compute
from riro.services.screens import (
    MONTHS,
    attention_badge,
    banner,
    bucket_columns,
    day_label,
    days_text,
    long_date,
    owner,
    problem_text,
    short_date,
    since_text,
    skipped_text,
    task_title,
)

SKIP = "no task number or description"


def test_us11_months_are_fixed_english_abbreviations():
    assert MONTHS == (
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


@pytest.mark.parametrize("month", range(1, 13))
def test_us11_long_and_short_dates_use_the_fixed_months(month):
    day = date(2026, month, 5)
    assert long_date(day) == f"05 {MONTHS[month - 1]} 2026"
    assert short_date(day) == f"5 {MONTHS[month - 1]}"


def test_us11_long_date_of_a_datetime_none_and_september():
    assert long_date(datetime(2026, 9, 1, 13, 5)) == "01 Sep 2026"
    assert long_date(None) == ""
    assert short_date(date(2026, 9, 30)) == "30 Sep"


@pytest.mark.parametrize(
    ("offset", "label"),
    [
        (0, "Day 0"),
        (1, "Day +1"),
        (5, "Day +5"),
        (-1, "Day -1"),
        (-10, "Day -10"),
        (None, "Deadline unclear"),
    ],
)
def test_us11_ladder_day_labels(offset, label):
    assert day_label(offset) == label


@pytest.mark.parametrize(
    ("track", "days", "expected"),
    [
        ("Delayed", -1, ("1 overdue", "neg")),
        ("Delayed", -3, ("3 overdue", "neg")),
        ("On Track", 0, ("Due today", "soon")),
        ("On Track", 1, ("1 left", "soon")),
        ("On Track", 2, ("2 left", "soon")),
        ("On Track", 3, ("3 left", "")),
        ("On Track", 12, ("12 left", "")),
        ("Completed Late", -2, ("2 late", "neg")),
        ("Completed", None, ("", "")),
        ("N/A", None, ("", "")),
        ("Deadline unclear", None, ("", "")),
        ("On Track", None, ("", "")),
        ("Delayed", None, ("", "")),
    ],
)
def test_us11_days_to_due_text_and_class(track, days, expected):
    assert days_text(track, days) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-1, ("1 day late", "Delayed")),
        (-4, ("4 days late", "Delayed")),
        (0, ("Today", "CompletedLate")),
    ],
)
def test_us11_attention_badge(days, expected):
    assert attention_badge(days) == expected


def test_us04_banner_delayed_singular():
    status = compute(SIX_TASKS, date(2026, 11, 2), date(2026, 11, 5))
    assert banner(status) == {
        "kind": "bad",
        "title": "Delayed",
        "text": "1 task is past deadline · 2 of 5 applicable tasks completed (40%)",
    }


def test_us04_banner_delayed_plural():
    tasks = [
        Task(
            2,
            "1",
            "PMO",
            "Invented task 1",
            "1 days After Roll On",
            "Not Started",
            None,
        ),
        Task(
            3,
            "2",
            "PMO",
            "Invented task 2",
            "1 days After Roll On",
            "In Progress",
            None,
        ),
        Task(
            4,
            "3",
            "PMO",
            "Invented task 3",
            "On Roll On",
            "Completed",
            date(2026, 11, 2),
        ),
    ]
    status = compute(tasks, date(2026, 11, 2), date(2026, 11, 5))
    assert (
        banner(status)["text"]
        == "2 tasks are past deadline · 1 of 3 applicable tasks completed (33%)"
    )
    assert banner(status)["kind"] == "bad"


def test_us04_banner_on_track():
    status = compute(SIX_TASKS, date(2026, 11, 9), date(2026, 11, 5))
    assert banner(status) == {
        "kind": "ok",
        "title": "On track",
        "text": "No open task is past its deadline · 2 of 5 applicable tasks completed (40%)",
    }


def test_us04_banner_with_no_applicable_task():
    na = [Task(2, "1", "PMO", "Invented task 1", "On Roll On", "Not Applicable", None)]
    status = compute(na, date(2026, 11, 2), date(2026, 11, 5))
    assert (
        banner(status)["text"]
        == "No open task is past its deadline · 0 of 0 applicable tasks completed (0%)"
    )


def test_us11_bucket_columns_with_date_lines():
    assert bucket_columns(date(2026, 11, 5)) == [
        {"key": "overdue", "label": "Overdue", "dates": "before 5 Nov"},
        {"key": "today", "label": "Today", "dates": "5 Nov"},
        {"key": "soon", "label": "1-3 days", "dates": "6-8 Nov"},
        {"key": "week", "label": "4-7 days", "dates": "9-12 Nov"},
        {"key": "later", "label": "Later", "dates": "after 12 Nov"},
    ]


def _dates(as_of):
    return [c["dates"] for c in bucket_columns(as_of)]


def test_us11_bucket_range_crossing_a_month_shows_both_months():
    assert _dates(date(2026, 10, 29)) == [
        "before 29 Oct",
        "29 Oct",
        "30 Oct-1 Nov",
        "2-5 Nov",
        "after 5 Nov",
    ]
    assert _dates(date(2026, 11, 25)) == [
        "before 25 Nov",
        "25 Nov",
        "26-28 Nov",
        "29 Nov-2 Dec",
        "after 2 Dec",
    ]


def test_us11_bucket_range_crossing_a_year_shows_both_months():
    assert _dates(date(2026, 12, 29)) == [
        "before 29 Dec",
        "29 Dec",
        "30 Dec-1 Jan",
        "2-5 Jan",
        "after 5 Jan",
    ]


@pytest.mark.parametrize(
    ("description", "title"),
    [
        ("Invented first line\nInvented second line", "Invented first line"),
        ("\n\n  Invented indented line  \nnext", "Invented indented line"),
        ("Invented line\r\nnext", "Invented line"),
        ("Only one line", "Only one line"),
        ("", ""),
        ("   \n  ", ""),
    ],
)
def test_us11_task_title_is_the_first_non_empty_line(description, title):
    assert task_title(description) == title


def _task(role, assigned_id=""):
    return Task(
        2,
        "1",
        role,
        "Invented task",
        "On Roll On",
        "Not Started",
        None,
        assigned_id=assigned_id,
    )


@pytest.mark.parametrize(
    "role", ["Team Member", "team member", "  TEAM MEMBER ", "Team  Member"]
)
def test_us11_team_member_task_owner_is_the_joiner(role):
    assert owner(_task(role, "invented.other"), "Alpha Example") == "Alpha Example"


def test_us11_other_roles_show_the_assigned_enterprise_id_or_nothing():
    assert (
        owner(_task("Hiring Manager", "invented.manager"), "Alpha Example")
        == "invented.manager"
    )
    assert owner(_task("Hiring Manager"), "Alpha Example") == ""


def test_us05_skipped_rows_text_singular_plural_and_none():
    assert skipped_text(()) == ""
    assert (
        skipped_text((SkippedRow(9, SKIP),))
        == f"1 row could not be read: {SKIP} (row 9)."
    )
    assert skipped_text((SkippedRow(9, SKIP), SkippedRow(14, SKIP))) == (
        f"2 rows could not be read: {SKIP} (rows 9, 14)."
    )


def test_us05_skipped_rows_with_different_reasons_list_each_reason_once_in_order():
    rows = (
        SkippedRow(9, "reason b"),
        SkippedRow(14, "reason a"),
        SkippedRow(20, "reason b"),
    )
    assert (
        skipped_text(rows)
        == "3 rows could not be read: reason b; reason a (rows 9, 14, 20)."
    )


def test_us09_problem_text():
    read_at = datetime(2026, 10, 29, 9, 0)
    assert problem_text(None, read_at) == ""
    assert problem_text("the file is locked", read_at) == (
        "File could not be read: the file is locked, showing data from 29 Oct 2026"
    )
    assert (
        problem_text("the file is locked", None)
        == "File could not be read: the file is locked."
    )


@pytest.mark.parametrize(
    ("since", "text"),
    [(3, "day 3"), (0, "day 0"), (-1, "1 day to go"), (-4, "4 days to go")],
)
def test_us11_since_text(since, text):
    assert since_text(since) == text
