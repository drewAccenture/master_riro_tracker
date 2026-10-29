"""US-07, US-06: the bridge passes the sync summary (counts, skipped files) and Connect starts auto-sync."""

import json
from datetime import datetime

import pytest

from riro.services.sync import SyncResult
from riro.ui.bridge import Bridge

SKIPPED = (
    ("Synthetic Joiner B.xlsx", "synthetic reason one"),
    ("Synthetic Joiner C.xlsx", "synthetic reason two"),
)
PARTIAL = SyncResult(
    "ok",
    "Sync partly worked: 1 of 3 files read. 2 files were skipped.",
    files_listed=4,
    last_success=datetime(2026, 10, 29, 9, 5),
    files_read=1,
    updated=1,
    unchanged=0,
    skipped=SKIPPED,
)
EXISTING_KEYS = {"state", "message", "files_listed", "report", "last_success"}


class FakeSync:
    def __init__(self, last, connect_result=None):
        self.last = last
        self.connect_result = connect_result or last

    def last_result(self):
        return self.last

    def is_running(self):
        return False

    def is_connected(self):
        return self.last.state == "ok"

    def sync(self):
        return self.last

    def connect(self):
        return self.connect_result


class FakeDiagnostics:
    def report(self):
        return "synthetic report text"


class FakeAutoSync:
    def __init__(self, running=False):
        self.calls = []
        self.is_running = running

    def running(self):
        return self.is_running

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


def test_us07_last_result_has_the_summary_fields():
    state = Bridge(FakeSync(PARTIAL), FakeDiagnostics()).last_result()
    assert (state["files_read"], state["updated"], state["unchanged"]) == (1, 1, 0)
    assert state["skipped"] == [
        {"name": "Synthetic Joiner B.xlsx", "reason": "synthetic reason one"},
        {"name": "Synthetic Joiner C.xlsx", "reason": "synthetic reason two"},
    ]
    assert EXISTING_KEYS <= set(state)
    assert state["message"] == PARTIAL.message
    assert state["files_listed"] == 4
    assert state["last_success"] == "29 Oct 2026 09:05"
    json.dumps(state)  # plain data only


def test_us07_sync_now_and_connect_have_the_summary_fields():
    bridge = Bridge(FakeSync(PARTIAL), FakeDiagnostics())
    for state in (bridge.sync_now(), bridge.connect()):
        assert state["skipped"][0] == {
            "name": "Synthetic Joiner B.xlsx",
            "reason": "synthetic reason one",
        }
        assert state["updated"] == 1
        assert EXISTING_KEYS <= set(state)


def test_us07_new_sync_result_fields_default_to_nothing():
    result = SyncResult("not_connected", "SharePoint: Not connected")
    assert (result.files_read, result.updated, result.unchanged, result.skipped) == (
        0,
        0,
        0,
        (),
    )
    state = Bridge(FakeSync(result), FakeDiagnostics()).last_result()
    assert (
        state["files_read"],
        state["updated"],
        state["unchanged"],
        state["skipped"],
    ) == (0, 0, 0, [])


def test_us06_connect_that_works_starts_auto_sync():
    auto = FakeAutoSync()
    bridge = Bridge(FakeSync(PARTIAL), FakeDiagnostics(), autosync=auto)
    bridge.connect()
    assert auto.calls == ["start"]


def test_us06_sign_in_that_worked_starts_auto_sync_even_if_its_first_sync_failed():
    # Review M1 (approved 2026-10-29): the sign-in finished, so the 5-minute timer must run again.
    auto = FakeAutoSync()
    sync = FakeSync(PARTIAL, connect_result=SyncResult("failed", "synthetic message"))
    Bridge(sync, FakeDiagnostics(), autosync=auto).connect()
    assert auto.calls == ["start"]


@pytest.mark.parametrize("state", ["sign_in_not_finished", "not_connected", "syncing"])
def test_us06_connect_that_does_not_work_does_not_start_auto_sync(state):
    auto = FakeAutoSync()
    sync = FakeSync(PARTIAL, connect_result=SyncResult(state, "synthetic message"))
    Bridge(sync, FakeDiagnostics(), autosync=auto).connect()
    assert auto.calls == []


def test_us06_last_result_and_sync_now_leave_a_running_auto_sync_alone():
    auto = FakeAutoSync(running=True)
    bridge = Bridge(FakeSync(PARTIAL), FakeDiagnostics(), autosync=auto)
    bridge.sync_now()
    bridge.last_result()
    assert auto.calls == []


@pytest.mark.parametrize("state", ["ok", "failed"])
def test_us06_sync_now_restarts_a_stopped_auto_sync(state):
    # Review M1: after a sign-in expiry, a Sync now that gets through brings the 5-minute timer back.
    auto = FakeAutoSync(running=False)
    sync = FakeSync(SyncResult(state, "synthetic message"))
    Bridge(sync, FakeDiagnostics(), autosync=auto).sync_now()
    assert auto.calls == ["start"]


@pytest.mark.parametrize("state", ["not_connected", "syncing"])
def test_us06_sync_now_that_is_not_connected_or_busy_does_not_start_auto_sync(state):
    auto = FakeAutoSync(running=False)
    sync = FakeSync(SyncResult(state, "synthetic message"))
    Bridge(sync, FakeDiagnostics(), autosync=auto).sync_now()
    assert auto.calls == []


def test_us06_connect_without_auto_sync_still_works():
    assert Bridge(FakeSync(PARTIAL), FakeDiagnostics()).connect()["state"] == "ok"


def test_page_still_sees_only_the_four_methods_with_auto_sync():
    bridge = Bridge(FakeSync(PARTIAL), FakeDiagnostics(), autosync=FakeAutoSync())
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == {"connect", "sync_now", "last_result", "copy_report"}
