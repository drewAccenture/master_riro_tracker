"""US-01, US-07, US-16: the bridge returns plain data for the page and exposes nothing else."""

import json
from datetime import datetime

from riro.core.models import HeaderReport
from riro.services.sync import FOLDER_LABEL, SyncResult
from riro.ui.bridge import Bridge

REPORT = HeaderReport(
    sheet_name="Test Person A",
    sheet_matched=False,
    headers_found=("Role",),
    headers_missing=("Deadline",),
    row_count=4,
)


class FakeSync:
    def __init__(self, last):
        self.last = last
        self.running = False
        self.calls = []

    def last_result(self):
        return self.last

    def is_running(self):
        return self.running

    def is_connected(self):
        return self.last.state == "ok"

    def sync(self):
        self.calls.append("sync")
        return self.last

    def connect(self):
        self.calls.append("connect")
        return SyncResult("sign_in_not_finished", "did not finish")


class FakeDiagnostics:
    def report(self):
        return "synthetic report text"


def make(last=None):
    sync = FakeSync(last or SyncResult("not_connected", "SharePoint: Not connected"))
    return Bridge(sync, FakeDiagnostics()), sync


def test_us01_not_connected_state_has_the_folder_filled_in():
    bridge, _ = make()
    state = bridge.last_result()
    assert state["connected"] is False
    assert state["folder"] == FOLDER_LABEL
    assert "In Progress Onboarding" in state["folder"]
    assert state["last_success"] == "Never"
    json.dumps(state)  # plain data only


def test_us07_ok_state_is_plain_data_with_time_and_no_sheet_name():
    last = SyncResult(
        "ok",
        "Sync OK",
        files_listed=3,
        report=REPORT,
        last_success=datetime(2026, 10, 27, 9, 5),
    )
    bridge, _ = make(last)
    state = bridge.last_result()
    assert state["connected"] is True
    assert state["last_success"] == "27 Oct 2026 09:05"
    assert state["report"] == {
        "headers_found": ["Role"],
        "headers_missing": ["Deadline"],
        "row_count": 4,
    }
    assert "Test Person A" not in json.dumps(state)


def test_us07_expired_sign_in_is_flagged_for_the_sign_in_again_button():
    expired = SyncResult(
        "not_connected", "Your SharePoint sign-in has expired. Click Sign in again."
    )
    bridge, _ = make(expired)
    assert bridge.last_result()["sign_in_expired"] is True
    bridge, _ = make()
    assert bridge.last_result()["sign_in_expired"] is False


def test_us07_running_sync_shows_syncing():
    bridge, sync = make(SyncResult("ok", "Sync OK"))
    sync.running = True
    state = bridge.last_result()
    assert state["running"] is True


def test_us07_sync_now_and_connect_call_the_service():
    bridge, sync = make()
    bridge.sync_now()
    result = bridge.connect()
    assert sync.calls == ["sync", "connect"]
    assert result["state"] == "sign_in_not_finished"
    assert result["message"] == "did not finish"


def test_us16_copy_report_returns_the_report_text():
    bridge, _ = make()
    assert bridge.copy_report() == {"text": "synthetic report text"}


def test_page_sees_only_the_four_methods():
    bridge, _ = make()
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == {"connect", "sync_now", "last_result", "copy_report"}
