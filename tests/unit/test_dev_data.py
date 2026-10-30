"""Slice 5b visual check (plan section 6): the dev-only RIRO_DATA_DIR switch and the synthetic demo data tool.

The demo folder never gets an edge_profile, so the app opens with no sign-in and no Edge.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path

from riro.__main__ import app_root
from riro.services.joiners import JoinerService
from riro.store.datafile import DataFile
from riro.store.repo import Repo, check_layout

TOOL = Path(__file__).resolve().parents[2] / "tools" / "make_demo_data.py"


def test_plan6_data_dir_switch_points_the_whole_app_at_another_folder(tmp_path):
    env = {"RIRO_DATA_DIR": str(tmp_path), "LOCALAPPDATA": r"C:\synthetic\local"}
    assert app_root(env) == tmp_path


def test_plan6_without_the_switch_the_app_uses_localappdata():
    env = {"LOCALAPPDATA": r"C:\synthetic\local"}
    assert app_root(env) == Path(r"C:\synthetic\local") / "RIROTracker"


def test_plan6_an_empty_switch_is_ignored():
    env = {"RIRO_DATA_DIR": "  ", "LOCALAPPDATA": r"C:\synthetic\local"}
    assert app_root(env) == Path(r"C:\synthetic\local") / "RIROTracker"


def test_plan6_demo_tool_writes_two_dated_joiners_and_one_waiting(tmp_path):
    done = subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    repo = Repo(DataFile(tmp_path / "data" / "tracker.json", validate=check_layout))
    assert repo.load_note is None
    views = JoinerService(repo).views(date.today())
    dated = [v for v in views if v.status is not None]
    waiting = [v for v in views if v.joiner.roll_on is None]
    assert len(dated) == 2
    assert len(waiting) == 1
    # US-05: different tiles per joiner.
    assert dated[0].status.counts != dated[1].status.counts
    assert not (tmp_path / "edge_profile").exists()


def test_plan6_demo_tool_refuses_a_folder_that_already_has_data(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tracker.json").write_text("{}", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode != 0
    assert (tmp_path / "data" / "tracker.json").read_text(encoding="utf-8") == "{}"
