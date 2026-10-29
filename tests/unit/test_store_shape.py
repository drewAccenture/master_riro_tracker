"""ADR-004 (review M2, M3, approved 2026-10-29): a data file with the wrong layout or a newer schema falls back to the
backup, a broken file that cannot be renamed never stops the app, and the restore note reaches the page.
Also the empty-ETag rule (review Low): a file without an ETag is always read again.
"""

import json
from datetime import datetime

from riro.core.checklist import read
from riro.core.models import FileRecord, SyncRun
from riro.services.sync import SyncResult
from riro.services.sync_files import sync_folder
from riro.store.datafile import RESTORED_FROM_BACKUP, STARTED_EMPTY, DataFile
from riro.store.repo import Repo, check_layout
from riro.ui.bridge import Bridge

T1 = datetime(2026, 10, 29, 9, 0)
T2 = datetime(2026, 10, 29, 9, 5)


def record(file_id, etag="e-1", checklist=None):
    return FileRecord(
        file_id,
        f"Synthetic {file_id}.xlsx",
        etag,
        "2026-10-20",
        True,
        checklist,
        T1,
        None,
    )


def saved_twice(tmp_path):
    """A data file whose .bak holds one good record "a" and whose main file holds "a" and "b"."""
    path = tmp_path / "data" / "tracker.json"
    repo = Repo(DataFile(path, validate=check_layout))
    repo.apply([record("a")], T1, SyncRun(T1, "ok", 1, 1, 0, ()))
    repo.apply([record("b")], T2, SyncRun(T2, "ok", 1, 1, 0, ()))
    return path


def test_adr004_main_file_with_wrong_layout_loads_the_backup(tmp_path):
    path = saved_twice(tmp_path)
    path.write_text(
        json.dumps({"schema_version": 1, "files": {"a": {"name": "only a name"}}}),
        encoding="utf-8",
    )
    repo = Repo(DataFile(path, validate=check_layout))
    assert repo.load_note == RESTORED_FROM_BACKUP
    assert [r.id for r in repo.files()] == ["a"]
    assert repo.last_success() == T1


def test_adr004_main_file_with_a_newer_schema_loads_the_backup(tmp_path):
    path = saved_twice(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "schema_version": 2}), encoding="utf-8")
    repo = Repo(DataFile(path, validate=check_layout))
    assert repo.load_note == RESTORED_FROM_BACKUP
    assert [r.id for r in repo.files()] == ["a"]


def test_adr004_broken_file_that_cannot_be_renamed_still_starts_empty(tmp_path):
    path = tmp_path / "tracker.json"
    path.write_bytes(b"{broken synthetic")

    def refuse(src, dst):
        raise PermissionError("synthetic: file held by antivirus")

    assert DataFile(path, replace=refuse).load() == (
        {"schema_version": 1},
        STARTED_EMPTY,
    )


class FakeSync:
    def last_result(self):
        return SyncResult("not_connected", "SharePoint: Not connected")

    def is_running(self):
        return False

    def is_connected(self):
        return False


def test_adr004_restore_note_reaches_the_page():
    state = Bridge(FakeSync(), None, data_note=RESTORED_FROM_BACKUP).last_result()
    assert state["data_note"] == RESTORED_FROM_BACKUP


def test_adr004_no_note_when_the_data_loaded_normally():
    assert Bridge(FakeSync(), None).last_result()["data_note"] is None


def test_us06_file_without_an_etag_is_read_again_every_sync(checklist_bytes):
    stored = {"a": record("a", etag="", checklist=read(checklist_bytes))}
    listing = [{"id": "a", "name": "Synthetic a.xlsx", "etag": "", "modified": "x"}]
    downloads = []

    def download(file_id):
        downloads.append(file_id)
        return checklist_bytes

    result = sync_folder(listing, stored, download, T2)
    assert downloads == ["a"]
    assert result.outcomes[0].kind == "updated"
