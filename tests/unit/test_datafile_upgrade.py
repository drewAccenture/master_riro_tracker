"""Slice 8a, US-15 (second criterion): an older data file is upgraded on load and a copy of it is kept first (ADR-004).

Given a newer package is installed over an older one, Then her roll-on dates and data are kept.
The real UPGRADES table is empty (SCHEMA_VERSION stays 1), so these tests pass their own test-only steps.
Names the code must provide are read from the module at test time, so each test fails on its own.
"""

import json

import pytest
from datafile_fakes import (
    FILES_A,
    FILES_B,
    NOW,
    STAMP,
    Steps,
    broken_copies,
    listing,
    needs,
    paths,
    version_copies,
    write_raw,
)

from riro.store import datafile
from riro.store.datafile import RESTORED_FROM_BACKUP, STARTED_EMPTY, DataFile

V1_COPY = f"tracker.json.v1-{STAMP}"


def store(path, steps_table, current=3, validate=None):
    kwargs = {"now": lambda: NOW, "schema_version": current, "upgrades": steps_table}
    if validate is not None:
        kwargs["validate"] = validate
    return DataFile(path, **kwargs)


# --- the table --------------------------------------------------------------------------------------------------


def test_us15_upgrades_table_exists_and_is_empty_while_schema_is_1():
    assert isinstance(datafile.UPGRADES, dict)
    assert datafile.UPGRADES == {}
    assert datafile.SCHEMA_VERSION == 1


# --- plan 4.1: older file, two steps ----------------------------------------------------------------------------


def test_us15_older_file_runs_steps_in_order_and_returns_current_version(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    steps = Steps(path.parent)
    data, note = store(path, steps.table(1, 2)).load()
    assert steps.calls == [1, 2]
    assert data == {"schema_version": 3, "files": FILES_A, "trail": [1, 2]}
    assert note is None


def test_us15_older_file_is_copied_byte_for_byte_before_the_first_step(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    steps = Steps(path.parent)
    store(path, steps.table(1, 2)).load()
    assert steps.copies_seen[0] == [V1_COPY]  # the copy was there when step 1 ran
    assert (path.parent / V1_COPY).read_bytes() == raw


def test_us15_load_does_not_rewrite_the_older_file(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    store(path, Steps(path.parent).table(1, 2)).load()
    assert path.read_bytes() == raw
    assert sorted(listing(path.parent)) == sorted(["tracker.json", V1_COPY])


def test_us15_upgrade_starts_at_the_files_own_version(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 2, "files": FILES_A, "trail": [1]})
    steps = Steps(path.parent)
    data, note = store(path, steps.table(1, 2)).load()
    assert steps.calls == [2]
    assert data == {"schema_version": 3, "files": FILES_A, "trail": [1, 2]}
    assert note is None
    assert version_copies(path.parent) == [f"tracker.json.v2-{STAMP}"]
    assert (path.parent / f"tracker.json.v2-{STAMP}").read_bytes() == raw


def test_us15_layout_check_runs_on_the_upgraded_data(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    steps = Steps(path.parent)
    data, note = store(path, steps.table(1, 2), validate=needs("trail")).load()
    assert note is None
    assert data["trail"] == [1, 2]


def test_us15_an_existing_version_copy_is_never_overwritten(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    earlier = path.parent / V1_COPY
    earlier.write_bytes(b"synthetic copy from an earlier upgrade")
    store(path, Steps(path.parent).table(1, 2)).load()
    assert earlier.read_bytes() == b"synthetic copy from an earlier upgrade"


def test_us15_next_save_writes_the_current_version_and_keeps_the_copy(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    first = store(path, Steps(path.parent).table(1, 2))
    data, _ = first.load()
    first.save(data)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 3
    assert on_disk["files"] == FILES_A
    assert (path.parent / V1_COPY).read_bytes() == raw
    steps = Steps(path.parent)
    assert store(path, steps.table(1, 2)).load() == (on_disk, None)
    assert steps.calls == []


# --- plan 4.2: a step that fails --------------------------------------------------------------------------------


def test_us15_failing_step_keeps_the_copy_and_uses_a_good_backup(tmp_path):
    path, bak, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    write_raw(bak, {"schema_version": 3, "files": FILES_B})
    data, note = store(path, Steps(path.parent, fail_at=2).table(1, 2)).load()
    assert (data, note) == (
        {"schema_version": 3, "files": FILES_B},
        RESTORED_FROM_BACKUP,
    )
    assert (path.parent / V1_COPY).read_bytes() == raw


def test_us15_failing_step_without_backup_starts_empty_and_renames_as_today(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    data, note = store(path, Steps(path.parent, fail_at=1).table(1, 2)).load()
    assert (data, note) == ({"schema_version": 3}, STARTED_EMPTY)
    assert (path.parent / V1_COPY).read_bytes() == raw
    assert (path.parent / f"tracker.json.broken-{STAMP}").read_bytes() == raw


def test_us15_upgraded_data_failing_the_layout_check_counts_as_broken(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    validate = needs("never-added-by-a-step")
    data, note = store(path, Steps(path.parent).table(1, 2), validate=validate).load()
    assert (data, note) == ({"schema_version": 3}, STARTED_EMPTY)
    assert (path.parent / V1_COPY).read_bytes() == raw


# --- plan 4.3: an older .bak with a broken main file ------------------------------------------------------------


@pytest.mark.parametrize(
    "main", [b"{not json, synthetic", None], ids=["broken", "missing"]
)
def test_us15_older_backup_is_upgraded_and_used(tmp_path, main):
    path, bak, _ = paths(tmp_path)
    if main is not None:
        path.parent.mkdir(parents=True)
        path.write_bytes(main)
    bak_raw = write_raw(bak, {"schema_version": 1, "files": FILES_B})
    steps = Steps(path.parent)
    data, note = store(path, steps.table(1, 2)).load()
    assert data == {"schema_version": 3, "files": FILES_B, "trail": [1, 2]}
    assert note == RESTORED_FROM_BACKUP
    assert steps.calls == [1, 2]
    assert bak.read_bytes() == bak_raw


def test_us15_older_backup_with_failing_step_and_broken_main_starts_empty(tmp_path):
    path, bak, _ = paths(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not json, synthetic")
    write_raw(bak, {"schema_version": 1, "files": FILES_B})
    data, note = store(path, Steps(path.parent, fail_at=1).table(1, 2)).load()
    assert (data, note) == ({"schema_version": 3}, STARTED_EMPTY)


# --- a missing step ---------------------------------------------------------------------------------------------


def test_us15_version_0_with_the_real_empty_table_counts_as_broken(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 0, "files": FILES_A})
    data, note = DataFile(path, now=lambda: NOW).load()
    assert (data, note) == ({"schema_version": 1}, STARTED_EMPTY)
    assert (path.parent / f"tracker.json.broken-{STAMP}").read_bytes() == raw


def test_us15_a_gap_in_the_steps_counts_as_broken_and_uses_the_backup(tmp_path):
    path, bak, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    write_raw(bak, {"schema_version": 3, "files": FILES_B})
    data, note = store(path, Steps(path.parent).table(1)).load()  # no step 2 -> 3
    assert (data, note) == (
        {"schema_version": 3, "files": FILES_B},
        RESTORED_FROM_BACKUP,
    )


@pytest.mark.parametrize("version", ["1", None, 1.5], ids=["text", "null", "float"])
def test_us15_schema_version_that_is_not_a_whole_number_counts_as_broken(
    tmp_path, version
):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": version, "files": FILES_A})
    steps = Steps(path.parent)
    data, note = store(path, steps.table(1, 2)).load()
    assert (data, note) == ({"schema_version": 3}, STARTED_EMPTY)
    assert broken_copies(path.parent) == [f"tracker.json.broken-{STAMP}"]


# --- plan 4.5: a current file is not copied ---------------------------------------------------------------------


def test_us15_current_file_with_defaults_makes_no_version_copy(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    assert DataFile(path, now=lambda: NOW).load() == (
        {"schema_version": 1, "files": FILES_A},
        None,
    )
    assert listing(path.parent) == {"tracker.json": raw}


def test_us15_current_file_runs_no_step_and_makes_no_copy(tmp_path):
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 3, "files": FILES_A})
    steps = Steps(path.parent)
    assert store(path, steps.table(1, 2)).load() == (
        {"schema_version": 3, "files": FILES_A},
        None,
    )
    assert steps.calls == []
    assert listing(path.parent) == {"tracker.json": raw}


def test_us15_upgrades_none_means_the_module_table(tmp_path, monkeypatch):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    steps = Steps(path.parent)
    monkeypatch.setattr(datafile, "UPGRADES", steps.table(1))
    data, note = DataFile(path, now=lambda: NOW, schema_version=2, upgrades=None).load()
    assert (data, note) == ({"schema_version": 2, "files": FILES_A, "trail": [1]}, None)
