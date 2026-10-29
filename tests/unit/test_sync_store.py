"""Plan slice 3 section 6, US-06, US-07, US-09, US-10, ADR-004: SyncService with a real Repo on tmp_path and a fake
folder. No Edge, no window, no network."""

import os
from datetime import datetime

import pytest
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.connectors.sharepoint import errors
from riro.core.checklist import read
from riro.core.models import SyncRun
from riro.services.sync import SAVE_FAILED, SyncService, message_for
from riro.services.sync_files import NO_ACCESS, NOT_FOUND, UNREADABLE
from riro.store.datafile import DataFile
from riro.store.repo import Repo

T1 = datetime(2026, 10, 29, 9, 0, 0)
T2 = datetime(2026, 10, 29, 9, 5, 0)
T3 = datetime(2026, 10, 29, 9, 10, 0)
T4 = datetime(2026, 10, 29, 9, 15, 0)
A, B, C = (
    "Synthetic Joiner A.xlsx",
    "Synthetic Joiner B.xlsx",
    "Synthetic Joiner C.xlsx",
)
BROKEN = b"PK\x03\x04 broken synthetic bytes"


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


@pytest.fixture
def folder(owner_file):
    f = Folder()
    f.put("id-a", A, owner_file("Test Person A"))
    f.put("id-b", B, owner_file("Test Person B"))
    f.put("id-c", C, owner_file("Test Person C"))
    return f


def make(folder, path, wall, **kwargs):
    diagnostics = FakeDiagnostics()
    repo = Repo(DataFile(path, **kwargs))
    service = SyncService(folder, diagnostics, repo=repo, clock=Clock(), now=wall)
    return service, repo, diagnostics


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "tracker.json"


def test_plan6_end_to_end_three_syncs_and_a_restart(folder, path, owner_file):
    wall = Wall(T1)
    service, repo, _ = make(folder, path, wall)
    old_b = read(folder.files["id-b"]["data"])

    first = service.sync()  # 1. all read
    assert first.state == "ok"
    assert first.message == "Sync OK: 3 joiners (3 updated, 0 unchanged)."
    assert (first.files_read, first.updated, first.unchanged, first.skipped) == (
        3,
        3,
        0,
        (),
    )
    assert first.last_success == T1
    assert folder.downloads == ["id-a", "id-b", "id-c"]
    assert [r.checklist.owner for r in repo.files()] == [
        "Test Person A",
        "Test Person B",
        "Test Person C",
    ]

    wall.t = T2  # 2. nothing changed: nothing downloaded (US-06)
    folder.downloads.clear()
    second = service.sync()
    assert folder.downloads == []
    assert second.message == "Sync OK: 3 joiners (0 updated, 3 unchanged)."
    assert second.last_success == T2

    wall.t = T3  # 3. B broken, C removed (US-09, US-10)
    folder.change("id-b", BROKEN, etag="e-id-b-2")
    folder.remove("id-c")
    third = service.sync()
    assert third.state == "ok"
    assert (
        third.message
        == "Sync partly worked: 2 joiners (0 updated). 1 file was skipped."
    )
    assert third.skipped == ((B, UNREADABLE),)
    assert third.last_success == T3
    b = repo.file("id-b")
    assert (b.checklist, b.problem, b.read_at, b.etag) == (
        old_b,
        UNREADABLE,
        T1,
        "e-id-b-1",
    )
    assert repo.file("id-c").present is False
    assert repo.file("id-c").checklist.owner == "Test Person C"
    assert repo.runs()[-1] == SyncRun(T3, "partial", 1, 0, 1, ((B, UNREADABLE),))
    assert [r.result for r in repo.runs()] == ["ok", "ok", "partial"]

    restarted = Repo(DataFile(path))  # 4. app restart
    assert restarted.last_success() == T3
    assert restarted.file("id-b").checklist == old_b
    assert restarted.file("id-b").problem == UNREADABLE
    assert restarted.file("id-c").present is False
    assert restarted.runs() == repo.runs()

    service2 = SyncService(
        folder, FakeDiagnostics(), repo=restarted, clock=Clock(), now=Wall(T4)
    )
    assert (
        service2.last_result().last_success == T3
    )  # "Last successful sync" survives a restart
    assert service2.is_connected() is False  # until a sync works
    folder.change("id-b", owner_file("Test Person B"), etag="e-id-b-3")
    fourth = service2.sync()
    assert fourth.message == "Sync OK: 2 joiners (1 updated, 1 unchanged)."
    assert restarted.file("id-b").problem is None
    assert service2.is_connected() is True


@pytest.mark.parametrize(
    ("kind", "reason"), [("NotFound", NOT_FOUND), ("NoAccess", NO_ACCESS)]
)
def test_us09_one_download_not_found_or_no_access_skips_only_that_file(
    folder, path, kind, reason
):
    service, repo, _ = make(folder, path, Wall(T1))
    folder.download_fail["id-b"] = getattr(errors, kind)("synthetic")
    result = service.sync()
    assert result.state == "ok"
    assert (
        result.message
        == "Sync partly worked: 2 joiners (2 updated). 1 file was skipped."
    )
    assert result.skipped == ((B, reason),)
    assert result.last_success == T1
    assert repo.file("id-a").checklist.owner == "Test Person A"
    assert repo.file("id-c").checklist.owner == "Test Person C"
    assert repo.file("id-b").checklist is None
    assert repo.file("id-b").problem == reason


def test_us07_two_skipped_files_use_the_plural(folder, path):
    service, _, _ = make(folder, path, Wall(T1))
    folder.change("id-a", BROKEN, etag="e-id-a-1")
    folder.download_fail["id-c"] = errors.NotFound("synthetic")
    result = service.sync()
    assert (
        result.message
        == "Sync partly worked: 1 joiner (1 updated). 2 files were skipped."
    )
    assert result.skipped == ((A, UNREADABLE), (C, NOT_FOUND))


def test_us07_report_is_from_the_first_readable_download(folder, path):
    service, _, diagnostics = make(folder, path, Wall(T1))
    folder.change("id-a", BROKEN, etag="e-id-a-1")
    result = service.sync()
    assert result.report is not None
    assert result.report.row_count == 2
    assert diagnostics.file_reports == [(2, 3, result.report)]


def test_us07_report_is_none_when_nothing_was_downloaded(folder, path):
    service, _, diagnostics = make(folder, path, Wall(T1))
    service.sync()
    diagnostics.file_reports.clear()
    again = service.sync()
    assert again.report is None
    assert diagnostics.file_reports == []


class Refusing:
    def __init__(self):
        self.on = False

    def __call__(self, src, dst):
        if self.on:
            raise PermissionError("synthetic: file in use")
        os.replace(src, dst)


def test_adr004_save_failed_fails_the_sync_and_keeps_the_old_data(
    folder, path, owner_file
):
    replace, wall = Refusing(), Wall(T1)
    service, repo, diagnostics = make(
        folder, path, wall, replace=replace, sleep=lambda s: None
    )
    assert service.sync().state == "ok"
    before = repo.files()
    replace.on = True
    wall.t = T2
    folder.change("id-a", owner_file("Test Person Z"), etag="e-id-a-2")
    result = service.sync()
    assert result.state == "failed"
    assert result.message == SAVE_FAILED
    assert result.last_success == T1
    assert repo.files() == before
    assert repo.last_success() == T1
    assert diagnostics.of("sync")[-1]["error_kind"] == "SaveFailed"
    assert Repo(DataFile(path)).file("id-a").checklist.owner == "Test Person A"


def test_adr004_save_failed_text():
    assert SAVE_FAILED == (
        "Your data could not be saved. Close other programs that may use it and click Sync now."
    )


@pytest.mark.parametrize(
    ("step", "error", "state"),
    [
        ("health_ping", errors.Unreachable(), "failed"),
        ("list_files", errors.Unreachable(), "failed"),
        ("list_files", errors.NeedsSignIn(), "not_connected"),
        ("download", errors.NeedsSignIn(), "not_connected"),
        ("download", errors.TimedOut(), "failed"),
    ],
)
def test_us07_failed_sync_keeps_data_and_adds_a_failed_run(
    folder, path, owner_file, step, error, state
):
    wall = Wall(T1)
    service, repo, _ = make(folder, path, wall)
    service.sync()
    before = repo.files()
    wall.t = T2
    folder.change("id-a", owner_file("Test Person Z"), etag="e-id-a-2")
    folder.fail[step] = error
    result = service.sync()
    assert result.state == state
    assert result.message == message_for(error)
    assert result.last_success == T1
    assert repo.files() == before
    assert repo.last_success() == T1
    assert [r.result for r in repo.runs()] == ["ok", "failed"]
    assert repo.runs()[-1].at == T2
    again = Repo(DataFile(path))
    assert again.files() == before
    assert again.runs()[-1].result == "failed"


def test_us07_failed_run_that_cannot_be_saved_still_reports_the_sync_error(
    folder, path
):
    replace = Refusing()
    service, _, _ = make(folder, path, Wall(T1), replace=replace, sleep=lambda s: None)
    replace.on = True
    folder.fail["list_files"] = errors.Unreachable()
    result = service.sync()
    assert result.state == "failed"
    assert result.message == message_for(errors.Unreachable())
