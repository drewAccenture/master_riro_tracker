"""Slice 8a, US-15 and ADR-006: install.bat replaces only app\\ and app.prev\\; data, edge_profile, logs stay.

Runs a copy of tools/package/install.bat with RIRO_INSTALL_TEST=1 (no shortcuts, no app start) and LOCALAPPDATA in
tmp_path, on a synthetic package: app\\pythonw.exe is a text file, never a real program. stdin is DEVNULL so the
`pause` on error paths returns at once instead of waiting for a key.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="install.bat runs on Windows only"
)

ROOT = Path(__file__).resolve().parents[2]
INSTALL_BAT = ROOT / "tools" / "package" / "install.bat"
TIMEOUT_S = 120

KEPT = {
    "data/tracker.json": b'{"schema_version": 1, "files": {"id-a": {"name": "Synthetic Joiner A.xlsx"}}}',
    "data/tracker.json.bak": b'{"schema_version": 1, "files": {}}',
    "edge_profile/Local State": b"synthetic edge local state",
    "edge_profile/Default/Preferences": b"synthetic edge preferences",
    "logs/riro.log": b"2026-11-03 09:00:00 synthetic log line\r\n",
}


def write_tree(folder, files):
    for rel, content in files.items():
        target = Path(folder) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def tree(folder):
    """{relative posix path: bytes} for every file under folder."""
    folder = Path(folder)
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file()
    }


def app_files(version, with_pythonw=True):
    files = {
        "riro/__init__.py": f"# synthetic riro {version}\n".encode(),
        "riro/web/index.html": f"<p>synthetic {version}</p>".encode(),
        f"only_in_{version}.txt": version.encode(),
    }
    if with_pythonw:
        files["pythonw.exe"] = f"not a program, synthetic {version}".encode()
    return files


def make_package(tmp_path, version, with_pythonw=True):
    package = tmp_path / f"package-{version}"
    write_tree(package / "app", app_files(version, with_pythonw))
    shutil.copyfile(INSTALL_BAT, package / "install.bat")
    return package


def existing_install(local, version="0.7.0"):
    target = local / "RIROTracker"
    write_tree(target, KEPT)
    write_tree(target / "app", app_files(version))
    return target


def assert_test_guard(script):
    """Review Low: the test mode must exit before the shortcuts and the app start, or the test would make real
    shortcuts (GetFolderPath ignores LOCALAPPDATA) and start the dummy pythonw.exe."""
    text = Path(script).read_text(encoding="utf-8", errors="replace")
    guard = text.find('if "%RIRO_INSTALL_TEST%"=="1" (')
    assert guard != -1, "install.bat lost its RIRO_INSTALL_TEST guard; not running it"
    assert "exit /b 0" in text[guard : guard + 200]
    for later in ("CreateShortcut", 'start ""'):
        assert guard < text.find(later), f"{later} comes before the test guard"


def test_us15_install_bat_test_guard_comes_before_shortcuts_and_start():
    assert_test_guard(INSTALL_BAT)


def run_install(package, local):
    assert_test_guard(package / "install.bat")
    env = {**os.environ, "LOCALAPPDATA": str(local), "RIRO_INSTALL_TEST": "1"}
    result = subprocess.run(
        ["cmd", "/c", str(package / "install.bat")],
        check=False,
        env=env,
        cwd=str(package),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=TIMEOUT_S,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    return result.returncode, output


def kept_part(target):
    return {
        k: v
        for k, v in tree(target).items()
        if k.split("/")[0] in ("data", "edge_profile", "logs")
    }


@pytest.fixture
def local(tmp_path):
    folder = tmp_path / "LocalAppData"
    folder.mkdir()
    return folder


# --- an upgrade -------------------------------------------------------------------------------------------------


def test_us15_install_over_older_keeps_data_edge_profile_and_logs_byte_for_byte(
    tmp_path, local
):
    target = existing_install(local)
    code, output = run_install(make_package(tmp_path, "0.8.0"), local)
    assert code == 0, output
    # the test mode was used: no shortcuts, no app start
    assert "Test install finished" in output
    assert kept_part(target) == KEPT


def test_us15_install_puts_the_new_app_in_place_and_the_old_one_in_app_prev(
    tmp_path, local
):
    target = existing_install(local)
    code, output = run_install(make_package(tmp_path, "0.8.0"), local)
    assert code == 0, output
    assert tree(target / "app") == app_files("0.8.0")
    assert tree(target / "app.prev") == app_files("0.7.0")


def test_us15_second_install_replaces_app_prev_with_the_previous_app(tmp_path, local):
    target = existing_install(local)
    code, output = run_install(make_package(tmp_path, "0.8.0"), local)
    assert code == 0, output
    code, output = run_install(make_package(tmp_path, "0.9.0"), local)
    assert code == 0, output
    assert tree(target / "app") == app_files("0.9.0")
    assert tree(target / "app.prev") == app_files("0.8.0")
    assert kept_part(target) == KEPT


def test_us15_first_install_creates_app_and_no_app_prev(tmp_path, local):
    code, output = run_install(make_package(tmp_path, "0.8.0"), local)
    assert code == 0, output
    target = local / "RIROTracker"
    assert tree(target / "app") == app_files("0.8.0")
    assert not (target / "app.prev").exists()
    assert not any(
        (target / name).exists() for name in ("data", "edge_profile", "logs")
    )


# --- an incomplete package --------------------------------------------------------------------------------------


def test_us15_package_without_pythonw_exits_non_zero_and_changes_nothing(
    tmp_path, local
):
    target = existing_install(local)
    write_tree(target / "app.prev", app_files("0.6.0"))
    before = tree(target)
    code, output = run_install(
        make_package(tmp_path, "0.8.0", with_pythonw=False), local
    )
    assert code != 0, output
    assert "pythonw.exe is missing" in output
    assert tree(target) == before


def test_us15_package_without_pythonw_creates_no_install_folder(tmp_path, local):
    code, output = run_install(
        make_package(tmp_path, "0.8.0", with_pythonw=False), local
    )
    assert code != 0, output
    assert not (local / "RIROTracker").exists()
