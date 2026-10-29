"""ADR-004: store/datafile.py, one JSON file with atomic saves, a .bak copy, retries and load fallbacks."""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from riro.store.datafile import (
    RESTORED_FROM_BACKUP,
    SCHEMA_VERSION,
    STARTED_EMPTY,
    DataFile,
    MemoryDataFile,
    SaveFailed,
)

BROKEN_AT = datetime(2026, 10, 29, 14, 3, 7)
DATA_A = {"files": {"id-a": {"name": "Synthetic Joiner A.xlsx"}}, "note": "first"}
DATA_B = {"files": {"id-b": {"name": "Synthetic Joiner B.xlsx"}}, "note": "second"}
BROKEN_CONTENTS = [b"", b"{not json at all", b"\xff\xfe\x00 zz synthetic garbage"]


def paths(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    return path, Path(str(path) + ".bak"), Path(str(path) + ".tmp")


def with_version(data):
    return {**data, "schema_version": 1}


class Replace:
    """os.replace that the test can make refuse (antivirus holding the file)."""

    def __init__(self, refuse_times=0, error=PermissionError):
        self.refuse_times = refuse_times
        self.error = error
        self.calls = []

    def __call__(self, src, dst):
        self.calls.append((str(src), str(dst)))
        if self.refuse_times:
            self.refuse_times -= 1
            raise self.error("synthetic: file in use")
        os.replace(src, dst)


class Sleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# --- constants -----------------------------------------------------------------------------------------------


def test_adr004_schema_version_starts_at_1():
    assert SCHEMA_VERSION == 1


def test_adr004_notes_are_plain_words():
    assert RESTORED_FROM_BACKUP == "Your data was restored from the backup copy."
    assert STARTED_EMPTY == (
        "Your data file was broken and no backup could be read. The app started with no data."
    )


# --- save ----------------------------------------------------------------------------------------------------


def test_adr004_missing_file_and_no_backup_start_empty_without_a_note(tmp_path):
    path, _, _ = paths(tmp_path)
    assert DataFile(path).load() == ({"schema_version": 1}, None)


def test_adr004_save_creates_folders_and_loads_back_equal(tmp_path):
    path, _, tmp = paths(tmp_path)
    store = DataFile(path)
    store.save(DATA_A)
    assert path.is_file()
    assert not tmp.exists()
    assert DataFile(path).load() == (with_version(DATA_A), None)


def test_adr004_saved_file_is_json_with_schema_version_1(tmp_path):
    path, _, _ = paths(tmp_path)
    DataFile(path).save(DATA_A)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 1
    assert on_disk["files"] == DATA_A["files"]


def test_adr004_save_writes_tmp_then_replaces_tracker_json(tmp_path):
    path, _, tmp = paths(tmp_path)
    replace = Replace()
    DataFile(path, replace=replace).save(DATA_A)
    assert replace.calls == [(str(tmp), str(path))]


def test_adr004_first_save_makes_no_backup(tmp_path):
    path, bak, _ = paths(tmp_path)
    DataFile(path).save(DATA_A)
    assert not bak.exists()


def test_adr004_next_save_copies_the_previous_file_to_bak(tmp_path):
    path, bak, _ = paths(tmp_path)
    store = DataFile(path)
    store.save(DATA_A)
    store.save(DATA_B)
    assert json.loads(bak.read_text(encoding="utf-8")) == with_version(DATA_A)
    assert store.load() == (with_version(DATA_B), None)


@pytest.mark.parametrize("error", [PermissionError, OSError])
def test_adr004_refused_replace_is_retried_200ms_apart_and_then_works(tmp_path, error):
    path, _, _ = paths(tmp_path)
    replace, sleep = Replace(refuse_times=2, error=error), Sleep()
    store = DataFile(path, replace=replace, sleep=sleep)
    store.save(DATA_A)
    assert len(replace.calls) == 3
    assert sleep.calls == [0.2, 0.2]
    assert store.load() == (with_version(DATA_A), None)


@pytest.mark.parametrize("error", [PermissionError, OSError])
def test_adr004_replace_refused_6_times_raises_save_failed_and_keeps_old_file(
    tmp_path, error
):
    path, _, _ = paths(tmp_path)
    DataFile(path).save(DATA_A)
    replace, sleep = Replace(refuse_times=99, error=error), Sleep()
    store = DataFile(path, replace=replace, sleep=sleep)
    with pytest.raises(SaveFailed):
        store.save(DATA_B)
    assert len(replace.calls) == 6  # 1 attempt + 5 retries
    assert sleep.calls == [0.2] * 5
    assert DataFile(path).load() == (with_version(DATA_A), None)


def test_adr004_save_failed_is_an_exception():
    assert issubclass(SaveFailed, Exception)


# --- load fallbacks ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("broken", BROKEN_CONTENTS)
def test_adr004_broken_file_with_good_backup_loads_backup_and_says_so(tmp_path, broken):
    path, _, _ = paths(tmp_path)
    store = DataFile(path)
    store.save(DATA_A)
    store.save(DATA_B)  # .bak now holds DATA_A
    path.write_bytes(broken)
    assert DataFile(path).load() == (with_version(DATA_A), RESTORED_FROM_BACKUP)


@pytest.mark.parametrize("broken", BROKEN_CONTENTS)
def test_adr004_both_broken_start_empty_and_keep_broken_file_renamed_with_date(
    tmp_path, broken
):
    path, bak, _ = paths(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(broken)
    bak.write_bytes(b"{also broken synthetic")
    store = DataFile(path, now=lambda: BROKEN_AT)
    assert store.load() == ({"schema_version": 1}, STARTED_EMPTY)
    kept = path.parent / "tracker.json.broken-20261029-140307"
    assert kept.read_bytes() == broken
    assert not path.exists() or path.read_bytes() != broken


def test_adr004_broken_file_and_no_backup_start_empty_and_keep_it(tmp_path):
    path, _, _ = paths(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not json")
    store = DataFile(path, now=lambda: BROKEN_AT)
    assert store.load() == ({"schema_version": 1}, STARTED_EMPTY)
    assert (path.parent / "tracker.json.broken-20261029-140307").is_file()


def test_adr004_save_after_starting_empty_works_and_loads_without_a_note(tmp_path):
    path, bak, _ = paths(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not json")
    bak.write_bytes(b"{not json")
    store = DataFile(path, now=lambda: BROKEN_AT)
    store.load()
    store.save(DATA_B)
    assert DataFile(path).load() == (with_version(DATA_B), None)


# --- in memory -----------------------------------------------------------------------------------------------


def test_adr004_memory_datafile_starts_empty():
    assert MemoryDataFile().load() == ({"schema_version": 1}, None)


def test_adr004_memory_datafile_round_trip_uses_copies():
    store = MemoryDataFile()
    data = {"files": {"id-a": {"name": "Synthetic Joiner A.xlsx"}}}
    store.save(data)
    data["files"]["id-a"]["name"] = "changed after save"
    loaded, note = store.load()
    assert note is None
    assert loaded == {
        "files": {"id-a": {"name": "Synthetic Joiner A.xlsx"}},
        "schema_version": 1,
    }
    loaded["files"].clear()
    assert store.load()[0]["files"] == {"id-a": {"name": "Synthetic Joiner A.xlsx"}}
