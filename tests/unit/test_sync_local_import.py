"""US-13, ADR-005: SyncService.import_files and how a sync treats imports. Fake folder, in-memory Repo, no Edge.

- An import works without SharePoint (no connector call).
- A sync never marks an import "left the folder"; a SharePoint file of the same owner replaces it, date kept.
- One thing at a time: an import while a sync runs returns BUSY and saves nothing.
"""

from datetime import datetime

import pytest
from import_fakes import SwitchDataFile, write_checklist
from joiner_fakes import D1
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.connectors.sharepoint import errors
from riro.services.joiners import JoinerService
from riro.services.local_import import (
    BUSY,
    IN_SHAREPOINT,
    TOO_LARGE,
    ImportResult,
    import_summary,
    local_id,
)
from riro.services.sync import SyncService
from riro.store.repo import Repo

T1 = datetime(2026, 10, 30, 9, 0, 0)
A = "Synthetic Joiner A.xlsx"
LOCAL_A = local_id("test person a")


@pytest.fixture
def owner_file(make_checklist, make_row):
    def _make(owner):
        return make_checklist(
            [
                make_row(1, "Invented task one", owner=owner),
                make_row(2, "Invented task two", status="Completed", owner=owner),
            ]
        )

    return _make


def make(folder=None):
    folder = folder if folder is not None else Folder()
    datafile = SwitchDataFile()
    repo, diagnostics = Repo(datafile), FakeDiagnostics()
    service = SyncService(folder, diagnostics, repo=repo, clock=Clock(), now=Wall(T1))
    return service, repo, diagnostics, datafile


def visible(repo):
    return [j for j in repo.joiners() if not j.hidden]


def test_us13_import_files_adds_a_waiting_joiner_through_the_service(tmp_path):
    service, repo, diagnostics, _ = make()
    result = service.import_files([write_checklist(tmp_path, A)])
    assert result == ImportResult("ok", import_summary(1, 0, 0), added=1)
    [j] = visible(repo)
    assert (j.file_id, j.roll_on) == (LOCAL_A, None)
    assert (
        repo.file(LOCAL_A).read_at == T1
    )  # the service's wall clock is the import time
    assert len(diagnostics.of("local_import")) == 1


def test_us13_import_works_when_sharepoint_is_offline(tmp_path):
    folder = Folder()
    for step in ("sign_in", "health_ping", "list_files", "download"):
        folder.fail[step] = errors.Unreachable()
    service, repo, _, _ = make(folder)
    result = service.import_files([write_checklist(tmp_path, A)])
    assert (result.state, result.added) == ("ok", 1)
    assert folder.calls == []  # no connector call for an import
    assert len(visible(repo)) == 1


def test_us13_import_files_passes_max_bytes(tmp_path):
    service, repo, _, _ = make()
    result = service.import_files([write_checklist(tmp_path, A)], max_bytes=10)
    assert result.skipped == ((A, TOO_LARGE),)
    assert repo.files() == ()


def test_us13_import_while_a_sync_runs_is_busy_and_saves_nothing(tmp_path):
    service, repo, _, datafile = make()
    path = write_checklist(tmp_path, A)
    assert service._running.acquire(blocking=False)
    try:
        result = service.import_files([path])
    finally:
        service._running.release()
    assert result == ImportResult("busy", BUSY)
    assert BUSY == "A sync is running. Try the import again in a moment."
    assert (repo.files(), repo.joiners(), datafile.saves) == ((), (), 0)


def test_us13_import_releases_the_lock_so_a_sync_can_run(tmp_path, owner_file):
    folder = Folder()
    folder.put("id-b", "Synthetic Joiner B.xlsx", owner_file("Test Person B"))
    service, _, _, _ = make(folder)
    service.import_files([write_checklist(tmp_path, A)])
    assert service.is_running() is False
    assert service.sync().state == "ok"
    assert service.import_files([write_checklist(tmp_path / "again", A)]).state == "ok"


def test_us13_sync_without_the_import_keeps_it_present_and_visible_with_its_date(
    tmp_path, owner_file
):
    folder = Folder()
    folder.put("id-b", "Synthetic Joiner B.xlsx", owner_file("Test Person B"))
    service, repo, _, _ = make(folder)
    service.import_files([write_checklist(tmp_path, A)])
    [imported] = visible(repo)
    JoinerService(repo).set_roll_on(imported.id, D1.isoformat())
    for _ in range(
        3
    ):  # also past the re-upload window: an import never "leaves the folder"
        assert service.sync().state == "ok"
    assert repo.file(LOCAL_A).present is True
    shown = {j.id: j for j in visible(repo)}
    assert imported.id in shown
    assert (shown[imported.id].file_id, shown[imported.id].roll_on) == (LOCAL_A, D1)
    assert len(shown) == 2


def test_adr005_sharepoint_file_of_the_same_owner_replaces_the_import_and_keeps_the_date(
    tmp_path, owner_file
):
    folder = Folder()
    service, repo, _, _ = make(folder)
    service.import_files([write_checklist(tmp_path, A, owner="Test Person A")])
    [imported] = visible(repo)
    JoinerService(repo).set_roll_on(imported.id, D1.isoformat())
    folder.put("id-a", A, owner_file(" test person A"))
    result = service.sync()
    assert result.state == "ok"
    assert (
        result.warnings == ()
    )  # no duplicate warning for an import and its SharePoint file
    assert repo.file(LOCAL_A).present is False  # kept as data
    [shown] = visible(repo)
    assert (shown.id, shown.file_id, shown.roll_on) == (imported.id, "id-a", D1)
    second = service.sync()
    assert second.warnings == ()
    assert [(j.id, j.file_id, j.roll_on) for j in visible(repo)] == [
        (imported.id, "id-a", D1)
    ]


def test_adr005_import_replaced_while_still_waiting_keeps_the_same_joiner(
    tmp_path, owner_file
):
    folder = Folder()
    service, repo, _, _ = make(folder)
    service.import_files([write_checklist(tmp_path, A, owner="Test Person A")])
    [imported] = visible(repo)
    folder.put("id-a", A, owner_file("Test Person A"))
    service.sync()
    [shown] = visible(repo)
    assert (shown.id, shown.file_id, shown.roll_on) == (imported.id, "id-a", None)


def test_us13_import_of_an_owner_already_in_sharepoint_is_skipped(tmp_path, owner_file):
    folder = Folder()
    folder.put("id-a", A, owner_file("Test Person A"))
    service, repo, _, _ = make(folder)
    service.sync()
    before = (repo.files(), repo.joiners())
    result = service.import_files(
        [write_checklist(tmp_path, "Synthetic local copy.xlsx", owner="test person a")]
    )
    assert result.skipped == (("Synthetic local copy.xlsx", IN_SHAREPOINT),)
    assert (repo.files(), repo.joiners()) == before


def test_us13_import_does_not_change_the_last_sync_or_its_runs(tmp_path, owner_file):
    folder = Folder()
    folder.put("id-b", "Synthetic Joiner B.xlsx", owner_file("Test Person B"))
    service, repo, _, _ = make(folder)
    service.sync()
    before = (repo.last_success(), repo.runs())
    service.import_files([write_checklist(tmp_path, A)])
    assert (repo.last_success(), repo.runs()) == before
