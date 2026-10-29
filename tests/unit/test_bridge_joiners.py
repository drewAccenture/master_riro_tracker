"""US-03, US-04, US-05, US-10: the bridge's joiners, joiner and set_roll_on methods return plain JSON data.

A real JoinerService over an in-memory Repo. "Status as of" comes from the page as yyyy-mm-dd (Assumption 7).
"""

import json

import pytest
from joiner_fakes import SIX_TASKS, SKIPPED, T1, joiner, rec, run

from riro.services.joiners import BAD_DATE, UNKNOWN_JOINER, JoinerService
from riro.services.sync import SyncResult
from riro.store.repo import Repo
from riro.ui.bridge import Bridge

AS_OF = "2026-11-05"


class FakeSync:
    def __init__(self, last=None):
        self.last = last or SyncResult("not_connected", "SharePoint: Not connected")

    def last_result(self):
        return self.last

    def is_running(self):
        return False

    def is_connected(self):
        return False

    def sync(self):
        return self.last

    def connect(self):
        return self.last


def make():
    repo = Repo.in_memory()
    records = [
        rec("f-z", owner="Zeta Person", tasks=SIX_TASKS),
        rec("f-a", owner="alpha Person", tasks=SIX_TASKS, skipped=SKIPPED),
        rec("f-b", owner="Beta Person", problem="synthetic reason"),
        rec("f-h", owner="Hidden Person", present=False, tasks=SIX_TASKS),
    ]
    joiners = [
        joiner("f-z", name="Zeta Person"),
        joiner("f-a", name="alpha Person"),
        joiner("f-b", name="Beta Person"),
        joiner("f-h", name="Hidden Person", hidden=True, missing_syncs=1),
    ]
    repo.apply(records, T1, run(), joiners=joiners)
    service = JoinerService(repo)
    service.set_roll_on("f-a", "2026-11-02")
    service.set_roll_on("f-h", "2026-11-02")
    return Bridge(FakeSync(), None, joiners=service)


def test_us03_joiners_lists_visible_joiners_with_waiting_flag_and_percent():
    result = make().joiners(AS_OF)
    assert result == {
        "joiners": [
            {
                "id": "f-a",
                "name": "alpha Person",
                "roll_on": "2026-11-02",
                "waiting": False,
                "percent": 40,
                "delayed_count": 1,
            },
            {
                "id": "f-b",
                "name": "Beta Person",
                "roll_on": None,
                "waiting": True,
                "percent": None,
                "delayed_count": None,
            },
            {
                "id": "f-z",
                "name": "Zeta Person",
                "roll_on": None,
                "waiting": True,
                "percent": None,
                "delayed_count": None,
            },
        ]
    }
    json.dumps(result)


def test_us10_hidden_joiners_are_not_listed():
    names = [j["name"] for j in make().joiners(AS_OF)["joiners"]]
    assert "Hidden Person" not in names


@pytest.mark.parametrize("as_of", ["", "05/11/2026", "tomorrow"])
def test_us04_bad_as_of_gives_the_bad_date_error(as_of):
    bridge = make()
    assert bridge.joiners(as_of) == {"error": BAD_DATE}
    assert bridge.joiner("f-a", as_of) == {"error": BAD_DATE}


def test_us04_joiner_with_a_date_has_tiles_percent_warnings_and_tasks():
    result = make().joiner("f-a", AS_OF)
    expected_tasks = [
        ("1", "On Roll On", "Completed", "2026-11-02", "Completed", "2026-11-02", None),
        ("2", "1 days After Roll On", "Not Started", None, "Delayed", "2026-11-03", -2),
        (
            "3",
            "10 days After Roll On",
            "In Progress",
            None,
            "On Track",
            "2026-11-12",
            7,
        ),
        ("4", "On Roll On", "Not Applicable", None, "N/A", "2026-11-02", None),
        (
            "5",
            "On Roll On",
            "Completed",
            "2026-11-05",
            "Completed Late",
            "2026-11-02",
            -3,
        ),
        ("6", "whenever it suits", "Not Started", None, "Deadline unclear", None, None),
    ]
    assert result == {
        "found": True,
        "id": "f-a",
        "name": "alpha Person",
        "roll_on": "2026-11-02",
        "waiting": False,
        "problem": None,
        "read_at": "29 Oct 2026 09:00",
        "percent": 40,
        "delayed": True,
        "delayed_count": 1,
        "counts": {
            "Delayed": 1,
            "On Track": 1,
            "Completed": 1,
            "Completed Late": 1,
            "N/A": 1,
            "Deadline unclear": 1,
        },
        "warnings": ["1 task has a deadline the app cannot read"],
        "skipped_rows": 1,
        "tasks": [
            {
                "number": number,
                "role": "PMO",
                "description": f"Invented task {number}",
                "deadline": deadline,
                "status": status,
                "completion_date": done_on,
                "track": track,
                "due": due,
                "days": days,
            }
            for number, deadline, status, done_on, track, due, days in expected_tasks
        ],
    }
    json.dumps(result)


def test_us03_waiting_joiner_has_tasks_but_no_status():
    result = make().joiner("f-z", AS_OF)
    assert result["found"] is True
    assert (result["roll_on"], result["waiting"]) == (None, True)
    assert (result["percent"], result["delayed"], result["delayed_count"]) == (
        None,
        None,
        None,
    )
    assert result["counts"] == {}
    assert len(result["tasks"]) == 6
    assert all(
        (t["track"], t["due"], t["days"]) == (None, None, None) for t in result["tasks"]
    )
    assert result["tasks"][4]["completion_date"] == "2026-11-05"
    assert result["skipped_rows"] == 0
    json.dumps(result)


def test_us09_joiner_shows_its_files_problem():
    result = make().joiner("f-b", AS_OF)
    assert result["problem"] == "synthetic reason"
    assert result["tasks"] == []


def test_us03_unknown_joiner_is_not_found():
    assert make().joiner("no-such-id", AS_OF) == {"found": False}


def test_us03_set_roll_on_moves_the_joiner_out_of_waiting():
    bridge = make()
    assert bridge.set_roll_on("f-z", "2026-11-02") == {"ok": True, "message": ""}
    listed = {j["id"]: j for j in bridge.joiners(AS_OF)["joiners"]}
    assert listed["f-z"]["waiting"] is False
    assert listed["f-z"]["roll_on"] == "2026-11-02"
    assert listed["f-z"]["percent"] == 40
    assert bridge.joiner("f-z", AS_OF)["delayed_count"] == 1


def test_us03_changed_date_shows_in_the_next_joiner_call():
    bridge = make()
    bridge.set_roll_on("f-a", "2026-11-09")
    result = bridge.joiner("f-a", AS_OF)
    assert result["roll_on"] == "2026-11-09"
    assert result["delayed_count"] == 0
    assert result["tasks"][1]["due"] == "2026-11-10"


def test_us03_set_roll_on_bad_date_and_unknown_joiner():
    bridge = make()
    assert bridge.set_roll_on("f-z", "02/11/2026") == {"ok": False, "message": BAD_DATE}
    assert bridge.set_roll_on("no-such-id", "2026-11-02") == {
        "ok": False,
        "message": UNKNOWN_JOINER,
    }


def test_us07_sync_state_has_joiner_counts_and_warnings():
    last = SyncResult(
        "ok",
        "Sync OK: 3 joiners (1 updated, 2 unchanged).",
        joiners=3,
        joiners_updated=1,
        warnings=("synthetic warning",),
    )
    state = Bridge(FakeSync(last), None).last_result()
    assert (state["joiners"], state["joiners_updated"]) == (3, 1)
    assert state["warnings"] == ["synthetic warning"]
    json.dumps(state)


def test_us07_sync_result_joiner_fields_default_to_nothing():
    result = SyncResult("not_connected", "SharePoint: Not connected")
    assert (result.joiners, result.joiners_updated, result.warnings) == (0, 0, ())
    state = Bridge(FakeSync(result), None).last_result()
    assert (state["joiners"], state["joiners_updated"], state["warnings"]) == (0, 0, [])
