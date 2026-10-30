"""US-13 (plan slice 6, section 3.5): the bridge's import_files() and the joiner "imported" flag. Plain JSON data.

Python opens the file dialog (pick_files), so the page never sends a path. A fake sync with import_files.
"""

import json

from joiner_fakes import SIX_TASKS, T1, joiner, rec, run

from riro.services.joiners import JoinerService
from riro.services.local_import import BUSY, NOT_XLSX, ImportResult, local_id
from riro.services.screens import Screens
from riro.services.sync import SyncResult
from riro.services.sync_files import UNREADABLE
from riro.services.sync_messages import SAVE_FAILED
from riro.store.repo import Repo
from riro.ui.bridge import Bridge

AS_OF = "2026-11-05"
LOCAL_B = local_id("test person b")
PATHS = [
    r"C:\synthetic\picked\Synthetic Joiner A.xlsx",
    r"C:\synthetic\picked\notes.txt",
]


class FakeSync:
    def __init__(self, result=None):
        self.result = result or ImportResult("ok", "synthetic summary")
        self.imports = []

    def last_result(self):
        return SyncResult("not_connected", "SharePoint: Not connected")

    def is_running(self):
        return False

    def is_connected(self):
        return False

    def import_files(self, paths):
        self.imports.append(list(paths))
        return self.result


class Picker:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.answer


def make(answer, result=None):
    sync, picker = FakeSync(result), Picker(answer)
    return Bridge(sync, None, pick_files=picker), sync, picker


def test_us13_cancelled_dialog_imports_nothing():
    for answer in (None, []):
        bridge, sync, picker = make(answer)
        assert bridge.import_files() == {"ok": True, "cancelled": True}
        assert picker.calls == 1
        assert sync.imports == []


def test_us13_picked_files_go_to_the_sync_service_and_the_result_is_plain_data():
    result = ImportResult(
        "ok",
        "synthetic summary",
        added=1,
        updated=2,
        skipped=(("notes.txt", NOT_XLSX), ("Synthetic Joiner C.xlsx", UNREADABLE)),
        warnings=("synthetic warning",),
    )
    bridge, sync, _ = make(PATHS, result)
    answer = bridge.import_files()
    assert sync.imports == [PATHS]
    assert answer == {
        "ok": True,
        "cancelled": False,
        "message": "synthetic summary",
        "added": 1,
        "updated": 2,
        "skipped": [
            {"name": "notes.txt", "reason": NOT_XLSX},
            {"name": "Synthetic Joiner C.xlsx", "reason": UNREADABLE},
        ],
        "warnings": ["synthetic warning"],
    }
    json.dumps(answer)


def test_us13_import_while_a_sync_runs_is_not_ok_with_the_busy_message():
    bridge, _, _ = make(PATHS, ImportResult("busy", BUSY))
    answer = bridge.import_files()
    assert (answer["ok"], answer["cancelled"], answer["message"]) == (
        False,
        False,
        BUSY,
    )
    assert (
        answer["added"],
        answer["updated"],
        answer["skipped"],
        answer["warnings"],
    ) == (0, 0, [], [])


def test_adr004_import_that_could_not_be_saved_is_not_ok():
    bridge, _, _ = make(PATHS, ImportResult("failed", SAVE_FAILED))
    answer = bridge.import_files()
    assert (answer["ok"], answer["cancelled"], answer["message"]) == (
        False,
        False,
        SAVE_FAILED,
    )


def joiner_bridges():
    repo = Repo.in_memory()
    records = [
        rec("id-a", owner="Test Person A", tasks=SIX_TASKS),
        rec(
            LOCAL_B,
            owner="Test Person B",
            tasks=SIX_TASKS,
            name="Synthetic Joiner B.xlsx",
        ),
    ]
    joiners = [
        joiner("id-a", name="Test Person A"),
        joiner(LOCAL_B, name="Test Person B"),
    ]
    repo.apply(records, T1, run(), joiners=joiners)
    service = JoinerService(repo)
    plain = Bridge(FakeSync(), None, joiners=service)
    rich = Bridge(FakeSync(), None, joiners=service, screens=Screens(service))
    return plain, rich


def test_us13_joiner_says_imported_for_a_local_file_only():
    plain, rich = joiner_bridges()
    for bridge in (plain, rich):
        assert bridge.joiner(LOCAL_B, AS_OF)["imported"] is True
        assert bridge.joiner("id-a", AS_OF)["imported"] is False
        json.dumps(bridge.joiner(LOCAL_B, AS_OF))


def test_us13_joiner_moved_to_sharepoint_is_no_longer_imported():
    repo = Repo.in_memory()
    records = [
        rec(LOCAL_B, owner="Test Person B", present=False),
        rec("id-b", owner="Test Person B"),
    ]
    repo.apply(
        records,
        T1,
        run(),
        joiners=[joiner(LOCAL_B, file_id="id-b", name="Test Person B")],
    )
    bridge = Bridge(FakeSync(), None, joiners=JoinerService(repo))
    assert (
        bridge.joiner(LOCAL_B, AS_OF)["imported"] is False
    )  # the flag follows the file, not the joiner id


def test_page_sees_only_the_nine_methods_with_import():
    bridge, _, _ = make(PATHS)
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == {
        "connect",
        "sync_now",
        "last_result",
        "copy_report",
        "joiners",
        "joiner",
        "set_roll_on",
        "overview",
        "import_files",
    }
