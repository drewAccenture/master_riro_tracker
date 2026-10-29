"""US-07, US-06: SyncService API changes for slice 3 (default repo, removed constant, summary on the fake folder)."""

from datetime import datetime

from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

import riro.services.sync as sync_module
from riro.core.models import FileRecord, SyncRun
from riro.services.sync import MESSAGES, SyncService
from riro.store.repo import Repo

T0 = datetime(2026, 10, 28, 17, 30, 0)
T1 = datetime(2026, 10, 29, 9, 0, 0)


def test_us07_unreadable_file_constant_left_sync_py():
    assert not hasattr(sync_module, "UNREADABLE_FILE")


def test_us07_timed_out_says_the_app_will_try_again():
    assert (
        MESSAGES["TimedOut"]
        == "SharePoint did not answer in time. The app will try again in 5 minutes."
    )


def test_us07_without_a_repo_the_service_uses_an_in_memory_one(checklist_bytes):
    folder = Folder()
    folder.put("id-1", "Synthetic Joiner A.xlsx", checklist_bytes)
    service = SyncService(folder, FakeDiagnostics(), clock=Clock(), now=Wall(T1))
    result = service.sync()
    assert result.state == "ok"
    assert result.message == "Sync OK: 1 files read (1 updated, 0 unchanged)."
    assert (result.files_read, result.updated, result.unchanged) == (1, 1, 0)


def test_us07_last_success_starts_from_the_repo(checklist_bytes):
    repo = Repo.in_memory()
    kept = FileRecord(
        id="id-1",
        name="Synthetic Joiner A.xlsx",
        etag="e-old",
        modified="2026-10-20",
        present=True,
        checklist=None,
        read_at=None,
        problem=None,
    )
    repo.apply([kept], T0, SyncRun(T0, "ok", 0, 0, 0, ()))
    folder = Folder()
    folder.put("id-1", "Synthetic Joiner A.xlsx", checklist_bytes)
    service = SyncService(
        folder, FakeDiagnostics(), repo=repo, clock=Clock(), now=Wall(T1)
    )
    assert service.last_result().state == "not_connected"
    assert service.last_result().last_success == T0
    assert service.is_connected() is False
    assert folder.calls == []


def test_us06_repo_is_used_by_the_sync(checklist_bytes):
    repo = Repo.in_memory()
    folder = Folder()
    folder.put("id-1", "Synthetic Joiner A.xlsx", checklist_bytes)
    service = SyncService(
        folder, FakeDiagnostics(), repo=repo, clock=Clock(), now=Wall(T1)
    )
    service.sync()
    assert repo.file("id-1").checklist is not None
    assert repo.last_success() == T1
    assert repo.runs() == (SyncRun(T1, "ok", 1, 1, 0, ()),)
