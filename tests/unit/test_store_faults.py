"""ADR-004, US-06 (review fixes): a failing save never destroys the good backup, never escapes as a raw OSError,
and never stops auto-sync.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.services.autosync import AutoSync
from riro.services.sync import SAVE_FAILED, SyncService
from riro.store.datafile import RESTORED_FROM_BACKUP, DataFile, SaveFailed
from riro.store.repo import Repo

T1 = datetime(2026, 10, 29, 9, 0)
DATA_A = {"note": "first"}
DATA_B = {"note": "second"}


def paths(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    return path, Path(f"{path}.bak"), Path(f"{path}.tmp")


def refuse(src, dst):
    raise PermissionError("synthetic: file in use")


def test_adr004_save_after_restore_keeps_the_good_backup_when_replace_fails(tmp_path):
    path, bak, _ = paths(tmp_path)
    store = DataFile(path)
    store.save(DATA_A)
    store.save(DATA_B)  # .bak holds DATA_A
    path.write_bytes(b"{broken synthetic")
    assert store.load()[1] == RESTORED_FROM_BACKUP

    with pytest.raises(SaveFailed):
        DataFile(path, replace=refuse, sleep=lambda s: None).save(DATA_B)

    assert json.loads(bak.read_text(encoding="utf-8"))["note"] == "first"
    assert DataFile(path).load() == (
        {**DATA_A, "schema_version": 1},
        RESTORED_FROM_BACKUP,
    )


def test_adr004_tmp_that_cannot_be_written_is_save_failed_and_old_file_stays(tmp_path):
    path, _, tmp = paths(tmp_path)
    DataFile(path).save(DATA_A)
    tmp.mkdir()  # opening the .tmp for writing now fails with an OSError
    with pytest.raises(SaveFailed):
        DataFile(path).save(DATA_B)
    assert DataFile(path).load()[0]["note"] == "first"


def test_adr004_backup_that_cannot_be_written_is_save_failed_and_old_file_stays(
    tmp_path,
):
    path, bak, _ = paths(tmp_path)
    DataFile(path).save(DATA_A)
    bak.mkdir()  # copying to .bak now fails with an OSError
    with pytest.raises(SaveFailed):
        DataFile(path).save(DATA_B)
    assert DataFile(path).load()[0]["note"] == "first"


def test_us07_sync_with_an_unwritable_data_file_fails_in_plain_words(
    tmp_path, checklist_bytes
):
    path, _, tmp = paths(tmp_path)
    repo = Repo(DataFile(path))
    tmp.parent.mkdir(parents=True)
    tmp.mkdir()
    folder = Folder()
    folder.put("id-1", "Synthetic Joiner A.xlsx", checklist_bytes)
    diagnostics = FakeDiagnostics()
    service = SyncService(folder, diagnostics, repo=repo, clock=Clock(), now=Wall(T1))

    result = service.sync()

    assert (result.state, result.message) == ("failed", SAVE_FAILED)
    assert result.last_success is None
    assert service.last_result() == result
    assert diagnostics.of("sync")[-1]["error_kind"] == "SaveFailed"


class FakeTimer:
    def __init__(self, interval, fn):
        self.fn = fn
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        pass


class Timers(list):
    def __call__(self, interval, fn):
        self.append(FakeTimer(interval, fn))
        return self[-1]


class Crashing:
    def sync(self):
        raise RuntimeError("synthetic crash inside a sync")


def test_us06_a_tick_whose_sync_raises_still_schedules_the_next_tick():
    timers = Timers()
    auto = AutoSync(Crashing(), timer_factory=timers)
    auto.start()
    with pytest.raises(RuntimeError):
        timers[0].fn()
    assert len(timers) == 2
    assert auto.running() is True
