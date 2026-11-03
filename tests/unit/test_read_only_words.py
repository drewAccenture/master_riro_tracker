"""Slice 8b (plan 3.3), US-07, ADR-013, ADR-015: the right words when the data file is read-only.

- DataFile.read_only / Repo.read_only (bool properties) and read_only_note (the load note, or None when writable).
- Read-only because a newer version wrote the file: a sync, a roll-on edit and an import show READ_ONLY,
  never SAVE_FAILED ("Close other programs" is wrong advice there).
- Read-only because an upgrade was not safe (ADR-015): they show UPGRADE_NOT_SAFE_MESSAGE.
- A normal SaveFailed (file writable, Windows refused) still shows the old words.

Real DataFile on tmp_path, fake SharePoint folder, synthetic checklist. Names the code must provide are read from the
module at test time, so each test fails on its own.
"""

import json
from datetime import datetime

import pytest
from datafile_fakes import NOW, STAMP, Steps, listing
from import_fakes import write_checklist
from store_sync_fakes import Clock, FakeDiagnostics, Folder, Wall

from riro.services import sync_messages
from riro.services.joiners import DATE_NOT_SAVED, JoinerService
from riro.services.sync import SAVE_FAILED, SyncService
from riro.store import datafile
from riro.store.datafile import NEWER_VERSION, DataFile, MemoryDataFile
from riro.store.repo import Repo, check_layout

T1 = datetime(2026, 11, 3, 9, 0)
T2 = datetime(2026, 11, 3, 9, 5)
READ_ONLY_TEXT = (
    "Your data was saved by a newer version of the tracker. "
    "Install the newer version again; nothing was changed."
)
NOT_SAFE_TEXT = (
    "Your data could not be upgraded safely. "
    "Restart the PC and open the tracker again; nothing was changed."
)


def seeded(tmp_path, checklist_bytes):
    """A current data file with one synced joiner (Test Person A), and the fake folder it came from."""
    path = tmp_path / "data" / "tracker.json"
    folder = Folder()
    folder.put("id-1", "Synthetic Joiner A.xlsx", checklist_bytes)
    repo = Repo(DataFile(path, validate=check_layout))
    result = SyncService(
        folder, FakeDiagnostics(), repo=repo, clock=Clock(), now=Wall(T1)
    ).sync()
    assert result.state == "ok"
    return path, folder


def newer_repo(tmp_path, checklist_bytes):
    """The same file as if a newer version saved it (schema_version 2), opened by this version."""
    path, folder = seeded(tmp_path, checklist_bytes)
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "schema_version": 2}), encoding="utf-8")
    return Repo(DataFile(path, validate=check_layout)), path, folder


def unsafe_repo(tmp_path, checklist_bytes):
    """The same (version 1) file opened by a build at version 3 whose safety copy has no free name (ADR-015)."""
    path, folder = seeded(tmp_path, checklist_bytes)
    for n in range(100):
        name = f"tracker.json.v1-{STAMP}" + (f"-{n}" if n else "")
        (path.parent / name).write_bytes(b"synthetic earlier copy")
    data_file = DataFile(
        path,
        now=lambda: NOW,
        validate=check_layout,
        schema_version=3,
        upgrades=Steps(path.parent).table(1, 2),
    )
    return Repo(data_file), path, folder


def service(repo, folder, diagnostics=None):
    return SyncService(
        folder, diagnostics or FakeDiagnostics(), repo=repo, clock=Clock(), now=Wall(T2)
    )


def picked_file(tmp_path):
    return write_checklist(
        tmp_path / "picked", "Synthetic Joiner B.xlsx", owner="Test Person B"
    )


# --- the words --------------------------------------------------------------------------------------------------


def test_us07_read_only_message_is_plain_words():
    assert sync_messages.READ_ONLY == READ_ONLY_TEXT
    assert sync_messages.READ_ONLY != SAVE_FAILED


def test_adr015_upgrade_not_safe_message_is_plain_words():
    assert sync_messages.UPGRADE_NOT_SAFE_MESSAGE == NOT_SAFE_TEXT


# --- the properties ---------------------------------------------------------------------------------------------


def test_us07_memory_data_file_and_in_memory_repo_are_writable():
    assert MemoryDataFile().read_only is False
    repo = Repo.in_memory()
    assert repo.read_only is False
    assert repo.read_only_note is None


def test_us07_current_file_is_writable_before_and_after_load(tmp_path, checklist_bytes):
    path, _ = seeded(tmp_path, checklist_bytes)
    data_file = DataFile(path, validate=check_layout)
    assert data_file.read_only is False
    data_file.load()
    assert data_file.read_only is False
    assert data_file.read_only_note is None


def test_adr013_newer_file_makes_data_file_and_repo_read_only(
    tmp_path, checklist_bytes
):
    repo, path, _ = newer_repo(tmp_path, checklist_bytes)
    assert repo.load_note == NEWER_VERSION
    assert repo.read_only is True
    assert repo.read_only_note == NEWER_VERSION
    data_file = DataFile(path, validate=check_layout)
    data_file.load()
    assert data_file.read_only is True
    assert data_file.read_only_note == NEWER_VERSION


def test_us07_read_only_is_a_property_that_cannot_be_set(tmp_path, checklist_bytes):
    repo, path, _ = newer_repo(tmp_path, checklist_bytes)
    data_file = DataFile(path)
    with pytest.raises(AttributeError):
        data_file.read_only = False
    with pytest.raises(AttributeError):
        repo.read_only = False


# --- read-only from a newer file: READ_ONLY ---------------------------------------------------------------------


def test_us07_sync_on_a_newer_file_shows_read_only_and_changes_nothing(
    tmp_path, checklist_bytes
):
    repo, path, folder = newer_repo(tmp_path, checklist_bytes)
    before = listing(path.parent)
    result = service(repo, folder).sync()
    assert result.state == "failed"
    assert result.message == sync_messages.READ_ONLY
    assert result.message != SAVE_FAILED
    assert result.last_success is None or result.last_success == T1
    assert listing(path.parent) == before


def test_us03_roll_on_edit_on_a_newer_file_shows_read_only(tmp_path, checklist_bytes):
    repo, path, _ = newer_repo(tmp_path, checklist_bytes)
    [joiner] = repo.joiners()
    before = listing(path.parent)
    ok, message = JoinerService(repo).set_roll_on(joiner.id, "2026-11-02")
    assert ok is False
    assert message == sync_messages.READ_ONLY
    assert message not in (SAVE_FAILED, DATE_NOT_SAVED)
    assert listing(path.parent) == before


def test_us13_import_on_a_newer_file_shows_read_only(tmp_path, checklist_bytes):
    repo, path, folder = newer_repo(tmp_path, checklist_bytes)
    picked = picked_file(tmp_path)
    before = listing(path.parent)
    result = service(repo, folder).import_files([picked])
    assert result.state == "failed"
    assert result.message == sync_messages.READ_ONLY
    assert result.message != SAVE_FAILED
    assert listing(path.parent) == before


# --- read-only from an unsafe upgrade (ADR-015): UPGRADE_NOT_SAFE_MESSAGE -----------------------------------------


def test_adr015_unsafe_upgrade_makes_the_repo_read_only(tmp_path, checklist_bytes):
    repo, _, _ = unsafe_repo(tmp_path, checklist_bytes)
    assert repo.read_only is True
    assert repo.read_only_note == datafile.UPGRADE_NOT_SAFE


def test_adr015_sync_after_an_unsafe_upgrade_shows_upgrade_not_safe(
    tmp_path, checklist_bytes
):
    repo, path, folder = unsafe_repo(tmp_path, checklist_bytes)
    before = listing(path.parent)
    result = service(repo, folder).sync()
    assert result.state == "failed"
    assert result.message == sync_messages.UPGRADE_NOT_SAFE_MESSAGE
    assert result.message not in (SAVE_FAILED, READ_ONLY_TEXT)
    assert listing(path.parent) == before


def test_adr015_import_after_an_unsafe_upgrade_shows_upgrade_not_safe(
    tmp_path, checklist_bytes
):
    repo, path, folder = unsafe_repo(tmp_path, checklist_bytes)
    picked = picked_file(tmp_path)
    before = listing(path.parent)
    result = service(repo, folder).import_files([picked])
    assert result.state == "failed"
    assert result.message == sync_messages.UPGRADE_NOT_SAFE_MESSAGE
    assert listing(path.parent) == before


# --- a normal SaveFailed keeps its words ------------------------------------------------------------------------


def writable_but_blocked(tmp_path, checklist_bytes):
    """A current file whose next save fails: the .tmp name is a folder (an OSError, as when another program holds it)."""
    path, folder = seeded(tmp_path, checklist_bytes)
    repo = Repo(DataFile(path, validate=check_layout))
    (path.parent / "tracker.json.tmp").mkdir()
    return repo, folder


def test_us07_normal_save_failure_on_sync_still_shows_save_failed(
    tmp_path, checklist_bytes
):
    repo, folder = writable_but_blocked(tmp_path, checklist_bytes)
    assert repo.read_only is False
    result = service(repo, folder).sync()
    assert (result.state, result.message) == ("failed", SAVE_FAILED)


def test_us03_normal_save_failure_on_roll_on_still_shows_date_not_saved(
    tmp_path, checklist_bytes
):
    repo, _ = writable_but_blocked(tmp_path, checklist_bytes)
    [joiner] = repo.joiners()
    assert JoinerService(repo).set_roll_on(joiner.id, "2026-11-02") == (
        False,
        DATE_NOT_SAVED,
    )


def test_us13_normal_save_failure_on_import_still_shows_save_failed(
    tmp_path, checklist_bytes
):
    repo, folder = writable_but_blocked(tmp_path, checklist_bytes)
    result = service(repo, folder).import_files([picked_file(tmp_path)])
    assert (result.state, result.message) == ("failed", SAVE_FAILED)
