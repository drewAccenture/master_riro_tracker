"""US-05, US-09, US-11 (plan slice 5, sections 3.1-3.2): Screens.joiner_extra(view, as_of), the joiner page data.

The tiles, meter, ladder and task rows always come from the selected joiner's own file (US-05).
"""

import json

import pytest
from joiner_fakes import T1, joiner, rec, run
from screens_fakes import AS_OF, make_service, t

from riro.services.joiners import JoinerService
from riro.services.screens import Screens
from riro.store.repo import Repo

THIRD = 100 / 6


def extra(joiner_id, service=None):
    service = service or make_service()
    return Screens(service).joiner_extra(service.joiner(joiner_id, AS_OF), AS_OF)


def test_us11_joiner_page_texts():
    result = extra("f-a")
    assert result["roll_on_text"] == "02 Nov 2026"
    assert result["as_of_text"] == "05 Nov 2026"
    assert (
        result["skipped_text"]
        == "1 row could not be read: no task number or description (row 9)."
    )
    assert result["problem_text"] == ""
    assert result["roles"] == ["PMO"]
    assert result["banner"] == {
        "kind": "bad",
        "title": "Delayed",
        "text": "1 task is past deadline · 2 of 5 applicable tasks completed (40%)",
    }


def test_us11_meter_is_a_list_of_plain_segments():
    meter = extra("f-a")["meter"]
    assert [(m["track"], m["count"]) for m in meter] == [
        ("Completed", 1),
        ("Completed Late", 1),
        ("On Track", 1),
        ("Delayed", 1),
    ]
    assert [m["percent"] for m in meter] == pytest.approx([THIRD] * 4)


def test_us05_five_tiles_follow_each_joiners_own_file():
    alpha, beta = extra("f-a")["tiles"], extra("f-b")["tiles"]
    assert alpha == [
        {"track": "Delayed", "label": "Delayed", "count": 1},
        {"track": "On Track", "label": "On Track", "count": 1},
        {"track": "Completed", "label": "Completed", "count": 1},
        {"track": "Completed Late", "label": "Completed Late", "count": 1},
        {"track": "N/A", "label": "Not applicable", "count": 1},
    ]
    assert [(x["track"], x["count"]) for x in beta] == [
        ("Delayed", 2),
        ("On Track", 4),
        ("Completed", 1),
        ("Completed Late", 0),
        ("N/A", 0),
    ]
    assert alpha != beta


def test_us11_ladder_columns_squares_and_marker():
    assert extra("f-a")["ladder"] == {
        "columns": [
            {
                "key": "d0",
                "label": "Day 0",
                "date": "2 Nov",
                "title": "3 tasks due 02 Nov 2026",
                "squares": [
                    {"index": 0, "track": "Completed", "css": "Completed"},
                    {"index": 4, "track": "Completed Late", "css": "CompletedLate"},
                    {"index": 3, "track": "N/A", "css": "NA"},
                ],
            },
            {
                "key": "d1",
                "label": "Day +1",
                "date": "3 Nov",
                "title": "1 task due 03 Nov 2026",
                "squares": [{"index": 1, "track": "Delayed", "css": "Delayed"}],
            },
            {
                "key": "d10",
                "label": "Day +10",
                "date": "12 Nov",
                "title": "1 task due 12 Nov 2026",
                "squares": [{"index": 2, "track": "On Track", "css": "OnTrack"}],
            },
            {
                "key": "unclear",
                "label": "Deadline unclear",
                "date": "",
                "title": "1 task with an unclear deadline",
                "squares": [
                    {"index": 5, "track": "Deadline unclear", "css": "Deadlineunclear"}
                ],
            },
        ],
        "marker_before": 2,
        "marker_label": "5 Nov",
    }


def test_us11_ladder_with_negative_offsets_keys_and_middle_marker():
    ladder = extra("f-b")["ladder"]
    assert [c["key"] for c in ladder["columns"]] == [
        "d-10",
        "d-7",
        "d-6",
        "d-4",
        "d-3",
        "d0",
        "d5",
    ]
    assert [c["label"] for c in ladder["columns"]][:2] == ["Day -10", "Day -7"]
    assert ladder["marker_before"] == 3  # d-4 is due 05 Nov, the "Status as of" day


def test_us11_unclear_column_title_plural():
    tasks = (t(1, "whenever it suits", "Not Started"), t(2, "ask someone", "Completed"))
    service = _service_with(tasks)
    column = extra("f-x", service)["ladder"]["columns"][-1]
    assert column["key"] == "unclear"
    assert column["title"] == "2 tasks with an unclear deadline"


def test_us11_task_rows_in_file_order_with_display_fields():
    rows = extra("f-a")["task_rows"]
    expected = [
        (0, "Due 02 Nov 2026", "", "", None, "d0", "02 Nov 2026"),
        (1, "Due 03 Nov 2026", "2 overdue", "neg", "overdue", "d1", ""),
        (2, "Due 12 Nov 2026", "7 left", "", "week", "d10", ""),
        (3, "Due 02 Nov 2026", "", "", None, "d0", ""),
        (4, "Due 02 Nov 2026", "3 late", "neg", None, "d0", "05 Nov 2026"),
        (5, "", "", "", None, "unclear", ""),
    ]
    assert rows == [
        {
            "index": index,
            "title": f"Invented task {index + 1}",
            "full": f"Invented task {index + 1}",
            "guidelines": "",
            "who": "",
            "due_text": due_text,
            "days_text": days_text,
            "days_css": days_css,
            "bucket": bucket,
            "ladder_key": key,
            "completion_text": done,
            "remarks": "",
        }
        for index, due_text, days_text, days_css, bucket, key, done in expected
    ]


def test_us11_task_rows_owner_title_and_buckets_for_other_roles():
    rows = extra("f-b")["task_rows"]
    assert [r["who"] for r in rows] == [
        "",
        "Beta Example",
        "invented.manager",
        "",
        "",
        "",
        "",
    ]
    assert rows[2]["title"] == "Invented first line"
    assert rows[2]["full"] == "Invented first line\nInvented second line"
    assert [r["bucket"] for r in rows] == [
        "week",
        "overdue",
        "overdue",
        None,
        "soon",
        "today",
        "later",
    ]
    assert (rows[5]["days_text"], rows[5]["days_css"]) == ("Due today", "soon")
    assert (rows[4]["days_text"], rows[4]["days_css"]) == ("1 left", "soon")


def test_us11_roles_are_sorted_distinct_and_non_empty():
    assert extra("f-b")["roles"] == ["Hiring Manager", "PMO", "Team Member"]


def test_us11_task_rows_carry_the_guidelines_text():
    tasks = (
        t(1, "On Roll On", "Not Started", guidelines="Invented guideline\nsecond line"),
    )
    rows = extra("f-x", _service_with(tasks))["task_rows"]
    assert rows[0]["guidelines"] == "Invented guideline\nsecond line"


def test_us03_waiting_joiner_has_rows_but_no_status_parts():
    result = extra("f-w")
    assert result["roll_on_text"] == ""
    assert result["as_of_text"] == "05 Nov 2026"
    assert (result["banner"], result["ladder"]) == (None, None)
    assert (result["meter"], result["tiles"]) == ([], [])
    rows = result["task_rows"]
    assert len(rows) == 6
    assert all(
        (r["due_text"], r["days_text"], r["days_css"], r["bucket"])
        == ("", "", "", None)
        for r in rows
    )
    assert rows[4]["completion_text"] == "05 Nov 2026"
    assert rows[0]["title"] == "Invented task 1"


def test_us09_file_problem_text_names_the_reason_and_the_last_good_read():
    service = make_service(problem="the file is locked")
    result = extra("f-a", service)
    assert result["problem_text"] == (
        "File could not be read: the file is locked, showing data from 29 Oct 2026"
    )
    assert len(result["task_rows"]) == 6  # the last good data stays on screen


def test_us05_no_skipped_rows_gives_no_skipped_text():
    assert extra("f-b")["skipped_text"] == ""


@pytest.mark.parametrize("joiner_id", ["f-a", "f-b", "f-w"])
def test_us11_joiner_extra_is_json_ready(joiner_id):
    result = extra(joiner_id)
    assert json.loads(json.dumps(result)) == result


def _service_with(tasks):
    repo = Repo.in_memory()
    repo.apply(
        [rec("f-x", owner="Extra Example", tasks=tasks)],
        T1,
        run(),
        joiners=[joiner("f-x", name="Extra Example", roll_on=AS_OF)],
    )
    return JoinerService(repo)
