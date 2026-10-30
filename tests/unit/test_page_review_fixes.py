"""Slice 5b review fixes (US-03, plan 3.5 and 6): a half-typed date never becomes a roll-on date, and the demo
switch is safe (absolute path only; the demo app cannot sign in, so real data never lands in a demo folder).
"""

from datetime import date

import pytest
from screens_fakes import make_service

from riro.__main__ import OfflineConnector, app_root, demo_mode
from riro.connectors.sharepoint.errors import ConnectorError
from riro.services.joiners import BAD_DATE, parse_date


@pytest.mark.parametrize(
    "text", ["0002-11-05", "0001-01-01", "1999-12-31", "2100-01-01", "9999-12-31"]
)
def test_us03_dates_outside_2000_to_2099_are_not_accepted(text):
    assert parse_date(text) is None


@pytest.mark.parametrize(
    "text, day", [("2000-01-01", date(2000, 1, 1)), ("2099-12-31", date(2099, 12, 31))]
)
def test_us03_dates_inside_the_range_are_accepted(text, day):
    assert parse_date(text) == day


def test_us03_half_typed_year_is_refused_by_set_roll_on():
    service = make_service()
    assert service.set_roll_on("f-w", "0002-11-05") == (False, BAD_DATE)
    assert service.joiner("f-w", date(2026, 11, 5)).joiner.roll_on is None


def test_plan6_relative_data_dir_is_ignored():
    env = {"RIRO_DATA_DIR": "demo", "LOCALAPPDATA": r"C:\synthetic\local"}
    assert app_root(env) == app_root({"LOCALAPPDATA": r"C:\synthetic\local"})


def test_plan6_demo_mode_only_with_an_absolute_data_dir(tmp_path):
    assert demo_mode({"RIRO_DATA_DIR": str(tmp_path)}) is True
    assert demo_mode({"RIRO_DATA_DIR": "demo"}) is False
    assert demo_mode({}) is False


@pytest.mark.parametrize("call", ["sign_in", "health_ping", "list_files"])
def test_plan6_demo_app_cannot_reach_sharepoint(call):
    with pytest.raises(ConnectorError):
        getattr(OfflineConnector(), call)()


def test_plan6_demo_connector_cannot_download():
    with pytest.raises(ConnectorError):
        OfflineConnector().download("any-id")


def test_plan6_demo_connector_closes_quietly():
    connector = OfflineConnector()
    connector.close()
    connector.shutdown()
