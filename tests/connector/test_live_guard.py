"""ADR-011: a live test needs both -m live and RIRO_LIVE=1, and uses a throwaway Edge profile only.

No live test runs here: these tests check the guard, the fixture and the pytest settings.
"""

import os
import tomllib
from pathlib import Path

import pytest
from sharepoint_fakes import LIVE, LIVE_REASON, assert_throwaway_profile

REPO = Path(__file__).resolve().parents[2]


def test_adr011_live_guard_marks_live_and_skips_without_riro_live():
    names = [mark.name for mark in LIVE]
    assert names == ["live", "skipif"]
    skipif = LIVE[1]
    assert skipif.kwargs["reason"] == LIVE_REASON
    condition = skipif.args[0]
    assert isinstance(condition, str)  # checked when the test runs, not at import
    assert eval(condition, {"os": os}) is (os.environ.get("RIRO_LIVE") != "1")


def test_adr011_pytest_settings_deselect_live_and_reject_unknown_markers():
    settings = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_settings = settings["tool"]["pytest"]["ini_options"]
    assert any(m.startswith("live:") for m in pytest_settings["markers"])
    assert "--strict-markers" in pytest_settings["addopts"]
    assert '-m "not live"' in pytest_settings["addopts"]


def test_adr011_check_script_runs_all_of_tests():
    script = (REPO / "tools" / "check.ps1").read_text(encoding="utf-8")
    assert "@('-m', 'pytest', 'tests', '-q')" in script
    assert "'tests\\unit'" not in script


def test_adr011_live_profile_is_a_throwaway_folder(live_profile, tmp_path):
    assert live_profile.name == "edge_profile"
    assert live_profile.resolve().is_relative_to(tmp_path.resolve())
    assert not live_profile.exists()  # Edge makes it; the test only hands over the path


@pytest.mark.parametrize(
    "forbidden",
    [
        Path("RIROTracker") / "edge_profile",
        Path("RIROTracker") / "data",
        Path("Microsoft") / "Edge" / "User Data" / "Default",
    ],
)
def test_adr011_app_and_everyday_edge_profiles_are_refused(forbidden):
    path = Path(os.environ["LOCALAPPDATA"]) / forbidden
    with pytest.raises(AssertionError, match="refusing"):
        assert_throwaway_profile(path)
