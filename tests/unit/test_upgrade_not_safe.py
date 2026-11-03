"""Slice 8b, ADR-015 (adds to ADR-004, ADR-013), US-15: no upgrade without its safety copy.

If the copy tracker.json.v<n>-<time> (or of .bak) cannot be written in full, no upgrade step runs, nothing is renamed
or written, a half-written copy is deleted, load returns ({"schema_version": <current>}, UPGRADE_NOT_SAFE) and every
save raises SaveFailed. The note reaches the report.

The copy is refused by replacing `open` in riro.store.datafile (the module's own seam; nothing else is patched),
or by taking every copy name on disk. Synthetic data, files under tmp_path only.
Names the code must provide are read from the module at test time, so each test fails on its own.
"""

import builtins
import re
from pathlib import Path

import pytest
from datafile_fakes import (
    FILES_A,
    FILES_B,
    NOW,
    STAMP,
    Steps,
    listing,
    paths,
    write_raw,
)

from riro.services.report_sections import data_lines
from riro.store import datafile
from riro.store.datafile import DataFile, SaveFailed
from riro.store.repo import Repo

NOT_SAFE_TEXT = (
    "Your data could not be upgraded safely. "
    "Restart the PC and open the tracker again; nothing was changed."
)
_COPY_NAME = re.compile(r"\.v\d+-\d{8}-\d{6}(-\d+)?$")


def is_copy(file) -> bool:
    return bool(_COPY_NAME.search(Path(str(file)).name))


def refuse_open(monkeypatch):
    """Opening any version copy is refused (no permission). Other files open as usual."""

    def fake_open(file, mode="r", *args, **kwargs):
        if is_copy(file):
            raise PermissionError(13, "synthetic: access denied", str(file))
        return builtins.open(file, mode, *args, **kwargs)

    monkeypatch.setattr(datafile, "open", fake_open, raising=False)


class HalfWriter:
    """A real file handle whose write() puts half the bytes on disk, then fails (disk full)."""

    def __init__(self, handle):
        self._handle = handle

    def write(self, data):
        self._handle.write(data[: len(data) // 2])
        self._handle.flush()
        raise OSError(28, "synthetic: no space left on device")

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()
        return False


def fail_mid_write(monkeypatch):
    def fake_open(file, mode="r", *args, **kwargs):
        # A stand-in for open(): the caller's `with` closes the handle.
        handle = builtins.open(file, mode, *args, **kwargs)  # noqa: SIM115
        return HalfWriter(handle) if is_copy(file) else handle

    monkeypatch.setattr(datafile, "open", fake_open, raising=False)


def take_all_names(folder: Path, base: str):
    """<base>.v1-<stamp> and -1 .. -99 all exist already (synthetic bytes)."""
    for n in range(100):
        name = f"{base}.v1-{STAMP}" + (f"-{n}" if n else "")
        (folder / name).write_bytes(f"synthetic earlier copy {n}".encode())


def block_copy(how, monkeypatch, folder, base):
    folder.mkdir(parents=True, exist_ok=True)
    if how == "open_refused":
        refuse_open(monkeypatch)
    elif how == "write_fails":
        fail_mid_write(monkeypatch)
    else:
        take_all_names(folder, base)


HOW = ["open_refused", "write_fails", "names_taken"]


def store(path, steps):
    return DataFile(path, now=lambda: NOW, schema_version=3, upgrades=steps.table(1, 2))


def assert_read_only(data_file, folder, tmp):
    before = listing(folder)
    for _ in range(2):
        with pytest.raises(SaveFailed):
            data_file.save({"files": FILES_B})
    assert listing(folder) == before
    assert not tmp.exists()


def test_adr015_note_is_plain_words():
    assert datafile.UPGRADE_NOT_SAFE == NOT_SAFE_TEXT


# --- an older main file -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("how", HOW)
def test_adr015_copy_not_written_means_no_step_and_nothing_changed(
    tmp_path, monkeypatch, how
):
    path, _, tmp = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    block_copy(how, monkeypatch, path.parent, "tracker.json")
    before = listing(path.parent)
    steps = Steps(path.parent)
    data_file = store(path, steps)

    assert data_file.load() == ({"schema_version": 3}, datafile.UPGRADE_NOT_SAFE)

    assert steps.calls == []
    assert path.read_bytes() == raw  # byte-for-byte, and not renamed
    assert listing(path.parent) == before  # no partial copy, no .broken-*, no .bak
    assert data_file.read_only is True
    assert data_file.read_only_note == datafile.UPGRADE_NOT_SAFE
    assert_read_only(data_file, path.parent, tmp)


@pytest.mark.parametrize("how", HOW)
def test_adr015_repo_on_an_unsafe_upgrade_is_read_only_with_the_note(
    tmp_path, monkeypatch, how
):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    block_copy(how, monkeypatch, path.parent, "tracker.json")
    repo = Repo(store(path, Steps(path.parent)))
    assert repo.load_note == datafile.UPGRADE_NOT_SAFE
    assert repo.read_only is True
    assert repo.read_only_note == datafile.UPGRADE_NOT_SAFE


def test_adr015_partial_copy_is_deleted(tmp_path, monkeypatch):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    fail_mid_write(monkeypatch)
    store(path, Steps(path.parent)).load()
    assert [p.name for p in path.parent.iterdir() if is_copy(p)] == []


def test_adr015_taken_copy_names_are_left_as_they_were(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    take_all_names(path.parent, "tracker.json")
    before = listing(path.parent)
    store(path, Steps(path.parent)).load()
    assert listing(path.parent) == before


def test_adr015_next_start_with_a_writable_copy_upgrades_as_usual(
    tmp_path, monkeypatch
):
    # "Restart the PC and open the tracker again": once the copy can be written, the slice 8a upgrade runs.
    path, _, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    refuse_open(monkeypatch)
    store(path, Steps(path.parent)).load()
    monkeypatch.undo()
    steps = Steps(path.parent)
    data_file = store(path, steps)
    data, note = data_file.load()
    assert steps.calls == [1, 2]
    assert note is None
    assert data == {"schema_version": 3, "files": FILES_A, "trail": [1, 2]}
    assert (path.parent / f"tracker.json.v1-{STAMP}").read_bytes() == raw
    assert data_file.read_only is False
    assert data_file.read_only_note is None


# --- an older .bak with a broken or missing main ----------------------------------------------------------------


@pytest.mark.parametrize(
    "main", [b"{not json, synthetic", None], ids=["broken", "missing"]
)
@pytest.mark.parametrize("how", HOW)
def test_adr015_older_backup_whose_copy_fails_changes_nothing(
    tmp_path, monkeypatch, how, main
):
    path, bak, tmp = paths(tmp_path)
    path.parent.mkdir(parents=True)
    if main is not None:
        path.write_bytes(main)
    bak_raw = write_raw(bak, {"schema_version": 1, "files": FILES_B})
    block_copy(how, monkeypatch, path.parent, "tracker.json.bak")
    before = listing(path.parent)
    steps = Steps(path.parent)
    data_file = store(path, steps)

    assert data_file.load() == ({"schema_version": 3}, datafile.UPGRADE_NOT_SAFE)

    assert steps.calls == []
    assert bak.read_bytes() == bak_raw
    assert path.exists() == (
        main is not None
    )  # a broken main is not renamed to .broken-*
    assert listing(path.parent) == before
    assert data_file.read_only is True
    assert_read_only(data_file, path.parent, tmp)


# --- the report (US-16) -----------------------------------------------------------------------------------------


def test_us16_upgrade_not_safe_note_is_in_the_report():
    lines = data_lines(Repo.in_memory(), datafile.UPGRADE_NOT_SAFE)
    assert f"data note: {NOT_SAFE_TEXT}" in lines


def test_us16_report_of_a_repo_opened_after_an_unsafe_upgrade_names_the_note(tmp_path):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    take_all_names(path.parent, "tracker.json")
    repo = Repo(store(path, Steps(path.parent)))
    assert f"data note: {NOT_SAFE_TEXT}" in data_lines(repo, repo.load_note)
