"""Plan slice 4 section 6 (US-02, US-03, US-10, ADR-005): SyncService + JoinerService + a real Repo on tmp_path and a
fake folder. Also: a roll-on date set while a sync runs is not lost by that sync's save. No Edge, no window."""

from datetime import date, datetime

import pytest
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.services.joiners import JoinerService
from riro.services.sync import SyncService
from riro.store.datafile import DataFile
from riro.store.repo import Repo, check_layout

T1 = datetime(2026, 10, 29, 9, 0, 0)
D1 = date(2026, 11, 2)
AS_OF = date(2026, 11, 5)
A, B = "Synthetic Joiner A.xlsx", "Synthetic Joiner B.xlsx"


@pytest.fixture
def owner_file(make_checklist, make_row):
    """Five tasks. Roll-on 2026-11-02, as of 2026-11-05: 1 Completed, 1 Delayed, 1 On Track, 1 N/A, 1 Late."""

    def _make(owner):
        return make_checklist(
            [
                make_row(
                    1,
                    "Invented task one",
                    "Completed",
                    datetime(2026, 11, 2),
                    owner=owner,
                ),
                make_row(
                    2, "Invented task two", deadline="1 days After Roll On", owner=owner
                ),
                make_row(
                    3,
                    "Invented task three",
                    "In Progress",
                    deadline="10 days After Roll On",
                    owner=owner,
                ),
                make_row(4, "Invented task four", "Not Applicable", owner=owner),
                make_row(
                    5,
                    "Invented task five",
                    "Completed",
                    datetime(2026, 11, 5),
                    owner=owner,
                ),
            ]
        )

    return _make


def open_app(folder, path, repo_class=Repo):
    repo = repo_class(DataFile(path, validate=check_layout))
    diagnostics = FakeDiagnostics()
    sync = SyncService(folder, diagnostics, repo=repo, clock=Clock(), now=Wall(T1))
    return sync, JoinerService(repo), repo, diagnostics


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "tracker.json"


def visible(joiners):
    return [
        (v.joiner.id, v.joiner.name, v.joiner.roll_on) for v in joiners.views(AS_OF)
    ]


def test_plan6_joiners_end_to_end_with_a_restart(path, owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Persn A"))
    folder.put("id-b", B, owner_file("Test Person B"))
    sync, joiners, _, diagnostics = open_app(folder, path)

    # 1. Two files appear: both joiners wait for a roll-on date.
    assert sync.sync().message == "Sync OK: 2 joiners (2 updated, 0 unchanged)."
    assert [j.id for j in joiners.waiting()] == ["id-a", "id-b"]
    assert all(v.status is None for v in joiners.views(AS_OF))

    # 2. A date is set for A.
    assert joiners.set_roll_on("id-a", "2026-11-02") == (True, "")
    assert [j.id for j in joiners.waiting()] == ["id-b"]

    # 3. A's owner text is corrected: same joiner, new name, date kept.
    folder.change("id-a", owner_file("Test Person A"), etag="e-id-a-2")
    assert sync.sync().message == "Sync OK: 2 joiners (1 updated, 1 unchanged)."
    assert visible(joiners) == [
        ("id-a", "Test Person A", D1),
        ("id-b", "Test Person B", None),
    ]

    # 4. A is deleted, and re-uploaded with a new id in the next sync: same joiner, date kept.
    folder.remove("id-a")
    sync.sync()
    assert visible(joiners) == [("id-b", "Test Person B", None)]
    folder.put("id-a2", A, owner_file("Test Person A"))
    assert sync.sync().message == "Sync OK: 2 joiners (1 updated, 1 unchanged)."
    assert diagnostics.of("sync")[-1]["moved_count"] == 1
    assert visible(joiners) == [
        ("id-a", "Test Person A", D1),
        ("id-b", "Test Person B", None),
    ]
    assert joiners.joiner("id-a", AS_OF).joiner.file_id == "id-a2"

    # 5. B leaves: hidden. B comes back: shown with its data.
    folder.remove("id-b")
    assert sync.sync().message == "Sync OK: 1 joiner (0 updated, 1 unchanged)."
    assert visible(joiners) == [("id-a", "Test Person A", D1)]
    assert joiners.waiting() == ()
    folder.put(
        "id-b", B, owner_file("Test Person B")
    )  # same ETag as before: not downloaded again
    folder.downloads.clear()
    assert sync.sync().message == "Sync OK: 2 joiners (0 updated, 2 unchanged)."
    assert folder.downloads == []
    b = joiners.joiner("id-b", AS_OF)
    assert (b.joiner.hidden, b.joiner.missing_syncs) == (False, 0)
    assert len(b.checklist.tasks) == 5

    # 6. App restart: everything is still there.
    sync2, joiners2, _, _ = open_app(folder, path)
    assert visible(joiners2) == [
        ("id-a", "Test Person A", D1),
        ("id-b", "Test Person B", None),
    ]
    assert [j.id for j in joiners2.waiting()] == ["id-b"]
    assert sync2.sync().message == "Sync OK: 2 joiners (0 updated, 2 unchanged)."
    a = joiners2.joiner("id-a", AS_OF)
    assert (a.joiner.roll_on, a.joiner.file_id) == (D1, "id-a2")
    assert a.status.counts == {
        "Delayed": 1,
        "On Track": 1,
        "Completed": 1,
        "Completed Late": 1,
        "N/A": 1,
        "Deadline unclear": 0,
    }
    assert (a.status.applicable, a.status.done, a.status.percent) == (4, 2, 50)
    assert (a.status.delayed, a.status.delayed_count, a.status.warnings) == (
        True,
        1,
        (),
    )
    assert [t.track for t in a.status.tasks] == [
        "Completed",
        "Delayed",
        "On Track",
        "N/A",
        "Completed Late",
    ]
    assert [t.days for t in a.status.tasks] == [None, -2, 7, None, -3]


class SettingFolder(Folder):
    """A folder whose listing step lets the PMO type a date on a second JoinerService (same repo)."""

    def __init__(self):
        super().__init__()
        self.on_list = None

    def list_files(self):
        if self.on_list is not None:
            hook, self.on_list = self.on_list, None
            hook()
        return super().list_files()


def test_us03_date_typed_while_a_sync_lists_files_is_not_lost(path, owner_file):
    folder = SettingFolder()
    folder.put("id-a", A, owner_file("Test Person A"))
    sync, joiners, repo, _ = open_app(folder, path)
    sync.sync()
    other = JoinerService(repo)
    folder.change("id-a", owner_file("Test Person A2"), etag="e-id-a-2")
    folder.on_list = lambda: other.set_roll_on("id-a", "2026-11-02")
    sync.sync()
    assert joiners.joiner("id-a", AS_OF).joiner.roll_on == D1
    assert joiners.joiner("id-a", AS_OF).joiner.name == "Test Person A2"
    assert Repo(DataFile(path)).joiners()[0].roll_on == D1


class RacingRepo(Repo):
    """Right after the sync reads the stored joiners, a date is typed (before the sync's one save)."""

    on_read = None

    def joiners(self):
        result = super().joiners()
        if self.on_read is not None:
            hook, self.on_read = self.on_read, None
            hook()
        return result


def test_us03_date_typed_after_the_sync_read_the_joiners_is_not_lost(path, owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    sync, _, repo, _ = open_app(folder, path, repo_class=RacingRepo)
    sync.sync()
    folder.change("id-a", owner_file("Test Person A2"), etag="e-id-a-2")
    repo.on_read = lambda: JoinerService(repo).set_roll_on("id-a", "2026-11-02")
    sync.sync()
    assert repo.on_read is None  # the sync did read the joiners
    assert repo.joiners()[0].roll_on == D1
    assert repo.joiners()[0].name == "Test Person A2"
    assert Repo(DataFile(path)).joiners()[0].roll_on == D1
