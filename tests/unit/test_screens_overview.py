"""US-03 totals, US-05, US-11 (plan slice 5, sections 3.1-3.2): Screens.overview(as_of), the "All joiners" data.

Waiting (no roll-on date) and hidden joiners never count in KPIs, heatmap rows or attention (plan default 2).
"""

import json

from screens_fakes import AS_OF, make_service

from riro.services.joiners import JoinerService
from riro.services.screens import Screens, bucket_columns
from riro.store.repo import Repo


def build(extra=True):
    return Screens(make_service(extra=extra)).overview(AS_OF)


def test_us11_overview_kpis_and_as_of_text():
    result = build()
    assert result["as_of_text"] == "05 Nov 2026"
    assert result["kpis"] == {
        "joiners": 2,
        "delayed": 3,
        "due_soon": 2,
        "average": "27%",
    }
    assert result["columns"] == bucket_columns(AS_OF)


def test_us11_heatmap_rows_with_cells_and_css():
    rows = build()["rows"]
    assert rows == [
        {
            "id": "f-a",
            "name": "Alpha Example",
            "roll_on_text": "02 Nov 2026",
            "since_text": "day 3",
            "percent": 40,
            "cells": [
                {"bucket": "overdue", "count": 1, "css": "hd"},
                {"bucket": "today", "count": 0, "css": "hz"},
                {"bucket": "soon", "count": 0, "css": "hz"},
                {"bucket": "week", "count": 1, "css": "ho"},
                {"bucket": "later", "count": 0, "css": "hz"},
            ],
        },
        {
            "id": "f-b",
            "name": "Beta Example",
            "roll_on_text": "09 Nov 2026",
            "since_text": "4 days to go",
            "percent": 14,
            "cells": [
                {"bucket": "overdue", "count": 2, "css": "hd"},
                {"bucket": "today", "count": 1, "css": "hw"},
                {"bucket": "soon", "count": 1, "css": "hw"},
                {"bucket": "week", "count": 1, "css": "ho"},
                {"bucket": "later", "count": 1, "css": "ho"},
            ],
        },
    ]


def test_us05_two_joiners_with_different_statuses_have_different_rows():
    alpha, beta = build()["rows"]
    assert [c["count"] for c in alpha["cells"]] != [c["count"] for c in beta["cells"]]
    assert alpha["percent"] != beta["percent"]


def test_us11_attention_items_sorted_with_title_who_and_badge():
    assert build()["attention"] == [
        {
            "joiner_id": "f-b",
            "joiner_name": "Beta Example",
            "task_index": 1,
            "task_number": "2",
            "title": "Invented task 2",
            "who": "Beta Example · Team Member",
            "badge": "6 days late",
            "badge_css": "Delayed",
        },
        {
            "joiner_id": "f-b",
            "joiner_name": "Beta Example",
            "task_index": 2,
            "task_number": "3",
            "title": "Invented first line",
            "who": "Beta Example · invented.manager, Hiring Manager",
            "badge": "3 days late",
            "badge_css": "Delayed",
        },
        {
            "joiner_id": "f-a",
            "joiner_name": "Alpha Example",
            "task_index": 1,
            "task_number": "2",
            "title": "Invented task 2",
            "who": "Alpha Example · PMO",
            "badge": "2 days late",
            "badge_css": "Delayed",
        },
        {
            "joiner_id": "f-b",
            "joiner_name": "Beta Example",
            "task_index": 5,
            "task_number": "6",
            "title": "Invented task 6",
            "who": "Beta Example · PMO",
            "badge": "Today",
            "badge_css": "CompletedLate",
        },
    ]


def test_us11_sidebar_lists_dated_joiners_with_line_and_pill_and_the_delayed_total():
    sidebar = build()["sidebar"]
    assert sidebar["delayed_total"] == 3
    assert sidebar["joiners"] == [
        {
            "id": "f-a",
            "name": "Alpha Example",
            "line": "Roll-on 02 Nov 2026 · 40% done",
            "delayed_count": 1,
        },
        {
            "id": "f-b",
            "name": "Beta Example",
            "line": "Roll-on 09 Nov 2026 · 14% done",
            "delayed_count": 2,
        },
    ]


def test_us03_waiting_joiner_is_only_in_the_waiting_list():
    result = build()
    assert result["sidebar"]["waiting"] == [{"id": "f-w", "name": "Waiting Example"}]
    assert "f-w" not in [j["id"] for j in result["sidebar"]["joiners"]]
    assert "f-w" not in [row["id"] for row in result["rows"]]
    assert "f-w" not in [item["joiner_id"] for item in result["attention"]]


def test_us03_waiting_and_hidden_joiners_change_no_kpi_row_or_attention_item():
    with_extra, without = build(extra=True), build(extra=False)
    for key in ("kpis", "rows", "attention"):
        assert with_extra[key] == without[key], key
    assert with_extra["sidebar"]["delayed_total"] == without["sidebar"]["delayed_total"]
    assert with_extra["sidebar"]["joiners"] == without["sidebar"]["joiners"]
    assert without["sidebar"]["waiting"] == []


def test_us10_hidden_joiner_shows_nowhere():
    text = json.dumps(build())
    assert "Hidden Example" not in text
    assert "f-h" not in text


def test_us03_typing_a_date_moves_the_waiting_joiner_into_the_totals():
    service = make_service()
    assert service.set_roll_on("f-w", "2026-11-02") == (True, "")
    result = Screens(service).overview(AS_OF)
    assert result["kpis"]["joiners"] == 3
    assert result["kpis"]["delayed"] == 4
    assert result["sidebar"]["waiting"] == []
    assert [j["id"] for j in result["sidebar"]["joiners"]] == ["f-a", "f-b", "f-w"]


def test_us11_no_joiners_gives_an_empty_overview():
    result = Screens(JoinerService(Repo.in_memory())).overview(AS_OF)
    assert result["kpis"] == {
        "joiners": 0,
        "delayed": 0,
        "due_soon": 0,
        "average": "0%",
    }
    assert (result["rows"], result["attention"]) == ([], [])
    assert result["sidebar"] == {"delayed_total": 0, "joiners": [], "waiting": []}


def test_us11_overview_is_json_ready():
    result = build()
    assert json.loads(json.dumps(result)) == result
