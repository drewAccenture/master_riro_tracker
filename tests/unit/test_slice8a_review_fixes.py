"""Slice 8a review fixes (US-15, US-16, ADR-004, ADR-013). Synthetic data only.

- The newer-version note reaches the diagnostic report.
- A newer file written over a current one after load: save refuses, changes nothing, and keeps refusing.
- After an upgrade, the first save puts the original old-layout bytes in .bak and makes no second copy.
- A far-out-of-range schema_version counts as broken and never stops the app.
"""

import pytest
from datafile_fakes import FILES_A, FILES_B, NOW, Steps, listing, paths, write_raw

from riro.services.report_sections import data_lines
from riro.store.datafile import NEWER_VERSION, STARTED_EMPTY, DataFile, SaveFailed
from riro.store.repo import Repo


def test_us16_newer_version_note_is_in_the_report():
    lines = data_lines(Repo.in_memory(), NEWER_VERSION)
    assert f"data note: {NEWER_VERSION}" in lines


def test_adr013_newer_file_written_after_load_is_never_overwritten(tmp_path):
    path, _, tmp = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    store = DataFile(path, now=lambda: NOW)
    store.load()
    write_raw(path, {"schema_version": 2, "files": FILES_B})
    before = listing(path.parent)
    for _ in range(2):
        with pytest.raises(SaveFailed):
            store.save({"files": FILES_A})
    assert listing(path.parent) == before
    assert not tmp.exists()


def test_us15_first_save_after_upgrade_keeps_the_original_in_bak_and_one_copy(
    tmp_path,
):
    path, bak, _ = paths(tmp_path)
    raw = write_raw(path, {"schema_version": 1, "files": FILES_A})
    store = DataFile(
        path, now=lambda: NOW, schema_version=3, upgrades=Steps(path.parent).table(1, 2)
    )
    data, _ = store.load()
    store.save(data)
    assert bak.read_bytes() == raw
    assert sorted(p.name for p in path.parent.glob("tracker.json*.v*-*")) == [
        "tracker.json.v1-20261103-091542"
    ]


def test_adr015_a_copy_this_run_did_not_create_is_never_deleted(tmp_path, monkeypatch):
    # Slice 8b review Low: open() refused on a name that exists (Windows: held, being deleted) -> keep that file.
    import builtins

    from riro.store import datafile

    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": 1, "files": FILES_A})
    held = path.parent / "tracker.json.v1-20261103-091542"
    held.write_bytes(b"synthetic copy held by another program")

    def refusing_open(file, mode="r", *args, **kwargs):
        if str(file) == str(held):
            raise PermissionError(13, "synthetic: access denied", str(file))
        return builtins.open(file, mode, *args, **kwargs)

    monkeypatch.setattr(datafile, "open", refusing_open, raising=False)
    store = DataFile(
        path, now=lambda: NOW, schema_version=3, upgrades=Steps(path.parent).table(1, 2)
    )
    assert store.load()[1] == datafile.UPGRADE_NOT_SAFE
    assert held.read_bytes() == b"synthetic copy held by another program"


@pytest.mark.parametrize("version", [-10_000_000_000_000, -1, 0])
def test_us15_out_of_range_version_counts_as_broken(tmp_path, version):
    path, _, _ = paths(tmp_path)
    write_raw(path, {"schema_version": version, "files": FILES_A})
    store = DataFile(
        path, now=lambda: NOW, schema_version=3, upgrades=Steps(path.parent).table(1, 2)
    )
    assert store.load() == ({"schema_version": 3}, STARTED_EMPTY)
