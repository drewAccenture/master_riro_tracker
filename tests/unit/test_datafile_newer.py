"""Slice 8a, US-15 and ADR-013: a data file from a newer version is opened read-only.

Going back to app.prev after an upgrade must not hide her data: the file is never renamed or written, the app
opens with that data (or empty when the layout check fails), and every save raises SaveFailed.
"""

import json

import pytest
from datafile_fakes import (
    FILES_A,
    FILES_B,
    NOW,
    Steps,
    listing,
    needs,
    paths,
    write_raw,
)

from riro.store import datafile
from riro.store.datafile import DataFile, SaveFailed

NEWER_TEXT = (
    "Your data was saved by a newer version of the tracker. "
    "Install the newer version again; nothing was changed."
)


def newer_main(tmp_path, version=2, files=FILES_A):
    path, bak, tmp = paths(tmp_path)
    data = {"schema_version": version, "files": files, "added_by_newer": {"x": 1}}
    write_raw(path, data)
    return path, bak, tmp, data


def assert_read_only(store, folder, tmp):
    before = listing(folder)
    for _ in range(2):
        with pytest.raises(SaveFailed):
            store.save({"files": FILES_B})
    assert listing(folder) == before
    assert not tmp.exists()


def test_adr013_newer_version_note_is_plain_words():
    assert datafile.NEWER_VERSION == NEWER_TEXT


# --- plan 4.4: a newer main file ---------------------------------------------------------------------------------


def test_adr013_newer_file_loads_its_data_with_the_note(tmp_path):
    path, _, _, data = newer_main(tmp_path)
    assert DataFile(path, now=lambda: NOW).load() == (data, NEWER_TEXT)


def test_adr013_newer_file_is_not_renamed_or_changed_or_copied_by_load(tmp_path):
    path, _, _, _ = newer_main(tmp_path)
    before = listing(path.parent)
    DataFile(path, now=lambda: NOW).load()
    assert listing(path.parent) == before  # no .broken-*, no .v*-*, same bytes


def test_adr013_every_save_after_a_newer_load_raises_and_changes_nothing(tmp_path):
    path, _, tmp, _ = newer_main(tmp_path)
    store = DataFile(path, now=lambda: NOW)
    store.load()
    assert_read_only(store, path.parent, tmp)


def test_adr013_newer_file_failing_the_layout_check_opens_empty_and_read_only(tmp_path):
    path, _, tmp, _ = newer_main(tmp_path)
    before = listing(path.parent)
    store = DataFile(path, now=lambda: NOW, validate=needs("never-there"))
    assert store.load() == ({"schema_version": 1}, NEWER_TEXT)
    assert listing(path.parent) == before
    assert_read_only(store, path.parent, tmp)


def test_adr013_newer_main_wins_over_a_good_current_backup(tmp_path):
    path, bak, tmp, data = newer_main(tmp_path)
    write_raw(bak, {"schema_version": 1, "files": FILES_B})
    before = listing(path.parent)
    store = DataFile(path, now=lambda: NOW)
    assert store.load() == (data, NEWER_TEXT)
    assert listing(path.parent) == before
    assert_read_only(store, path.parent, tmp)


def test_adr013_newer_than_a_custom_current_version_runs_no_step(tmp_path):
    path, _, tmp, data = newer_main(tmp_path, version=4)
    steps = Steps(path.parent)
    store = DataFile(
        path, now=lambda: NOW, schema_version=3, upgrades=steps.table(1, 2)
    )
    assert store.load() == (data, NEWER_TEXT)
    assert steps.calls == []
    assert_read_only(store, path.parent, tmp)


# --- only the .bak is newer --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "main", [None, b"{not json, synthetic"], ids=["missing", "broken"]
)
def test_adr013_newer_backup_with_bad_main_is_read_only_and_nothing_renamed(
    tmp_path, main
):
    path, bak, tmp = paths(tmp_path)
    if main is not None:
        path.parent.mkdir(parents=True)
        path.write_bytes(main)
    bak_data = {"schema_version": 2, "files": FILES_B}
    write_raw(bak, bak_data)
    before = listing(path.parent)
    store = DataFile(path, now=lambda: NOW)
    assert store.load() == (bak_data, NEWER_TEXT)
    assert listing(path.parent) == before
    assert_read_only(store, path.parent, tmp)
    assert path.exists() == (main is not None)


def test_adr013_newer_backup_failing_layout_check_opens_empty_and_read_only(tmp_path):
    path, bak, tmp = paths(tmp_path)
    write_raw(bak, {"schema_version": 2, "files": FILES_B})
    before = listing(path.parent)
    store = DataFile(path, now=lambda: NOW, validate=needs("never-there"))
    assert store.load() == ({"schema_version": 1}, NEWER_TEXT)
    assert listing(path.parent) == before
    assert_read_only(store, path.parent, tmp)


# --- a normal file stays writable --------------------------------------------------------------------------------


def test_adr013_current_file_still_saves_after_load(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    store = DataFile(path, now=lambda: NOW)
    store.load()
    store.save({"files": FILES_B})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "files": FILES_B,
    }
