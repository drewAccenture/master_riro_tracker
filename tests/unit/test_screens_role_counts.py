"""Visual-check decision (2026-10-29, option B): picking a role makes the joiner page's banner, meter, tiles and
ladder count only that role's tasks. The sidebar and overview stay whole-joiner. Counts still come from
core.status.compute, never from the page.

Beta's tasks by role (screens_fakes.BETA_TASKS): PMO = 0 On Track, 3 Completed, 4 On Track, 5 On Track;
Team Member = 1 Delayed; Hiring Manager = 2 Delayed; 6 has no role.
"""

import json

from screens_fakes import AS_OF, make_service

from riro.services.screens import Screens
from riro.ui.bridge import Bridge


def extra(role="", joiner_id="f-b"):
    service = make_service()
    return Screens(service).joiner_extra(
        service.joiner(joiner_id, AS_OF), AS_OF, role=role
    )


def counts(result):
    return {tile["track"]: tile["count"] for tile in result["tiles"]}


def test_role_filter_counts_only_that_roles_tasks():
    assert counts(extra("PMO")) == {
        "Delayed": 0,
        "On Track": 3,
        "Completed": 1,
        "Completed Late": 0,
        "N/A": 0,
    }
    assert counts(extra("Team Member"))["Delayed"] == 1
    assert sum(counts(extra("Team Member")).values()) == 1


def test_no_role_counts_the_whole_checklist():
    assert counts(extra("")) == counts(extra())
    assert sum(counts(extra()).values()) == 7


def test_role_banner_and_meter_follow_the_role():
    pmo = extra("PMO")
    assert pmo["banner"] == {
        "kind": "ok",
        "title": "On track",
        "text": "No open task is past its deadline · 1 of 4 applicable tasks completed (25%)",
    }
    assert [m["track"] for m in pmo["meter"]] == ["Completed", "On Track"]
    assert extra("Hiring Manager")["banner"]["kind"] == "bad"


def test_role_ladder_has_only_that_roles_tasks_with_their_real_indices():
    squares = [
        sq["index"]
        for column in extra("PMO")["ladder"]["columns"]
        for sq in column["squares"]
    ]
    assert sorted(squares) == [0, 3, 4, 5]


def test_task_rows_are_never_dropped_by_the_role_count():
    # The page hides rows; only the counts change.
    assert len(extra("PMO")["task_rows"]) == 7


def test_role_note_says_what_the_counts_cover():
    assert extra("PMO")["role_note"] == "Counts for role PMO: 4 of 7 tasks."
    assert extra("")["role_note"] == ""


def test_unknown_role_counts_nothing_without_failing():
    result = extra("No Such Role")
    assert sum(counts(result).values()) == 0
    assert result["ladder"]["columns"] == []
    assert result["role_note"] == "Counts for role No Such Role: 0 of 7 tasks."
    json.dumps(result)


class FakeSync:
    pass


def test_bridge_joiner_passes_the_role_and_keeps_the_whole_joiner_top_keys():
    service = make_service()
    bridge = Bridge(FakeSync(), None, joiners=service, screens=Screens(service))
    whole = bridge.joiner("f-b", "2026-11-05")
    pmo = bridge.joiner("f-b", "2026-11-05", "PMO")
    assert {t["track"]: t["count"] for t in pmo["tiles"]}["On Track"] == 3
    # The existing top-level keys (used by the sidebar list and older callers) stay whole-joiner.
    assert (pmo["percent"], pmo["delayed_count"], pmo["counts"]) == (
        whole["percent"],
        whole["delayed_count"],
        whole["counts"],
    )
