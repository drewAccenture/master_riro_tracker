"""US-01, ADR-002: at start the app checks only that the edge_profile folder exists; nothing inside it is touched."""

import builtins
import io
import os
from pathlib import Path

from riro.__main__ import signed_in_before


def watch_paths(monkeypatch, profile):
    root = os.path.normcase(os.path.abspath(profile))
    inside, folder = [], []

    def note(name, path):
        if isinstance(path, int):
            return
        full = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        if full == root:
            folder.append(name)
        elif full.startswith(root + os.sep):
            inside.append((name, full))

    def watch(module, name):
        real = getattr(module, name)

        def wrapper(path=".", *args, **kwargs):
            note(name, path)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(module, name, wrapper)

    for module, name in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "listdir"),
        (os, "scandir"),
        (os, "stat"),
        (os, "lstat"),
        (os.path, "isdir"),
        (os.path, "exists"),
    ]:
        watch(module, name)
    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self, *a, **k: note("Path.exists", self) or real_exists(self, *a, **k),
    )
    return inside, folder


def test_us01_profile_check_looks_at_the_folder_only(tmp_path, monkeypatch):
    profile = tmp_path / "edge_profile"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Cookies").write_bytes(b"synthetic, never read")
    inside, folder = watch_paths(monkeypatch, profile)

    assert signed_in_before(profile) is True
    assert inside == []  # nothing inside the folder was opened, listed or checked
    assert folder  # the folder itself was checked (proves the watch works)


def test_us01_no_profile_folder_means_not_signed_in_before(tmp_path):
    assert signed_in_before(tmp_path / "edge_profile") is False
