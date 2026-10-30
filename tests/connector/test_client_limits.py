"""US-01, US-07, ADR-003: time limits in client.py, killing a stuck Edge, a fresh Edge next time, visible sign-in.

Fake Edge launcher and fake pages (sharepoint_fakes.py). A fake clock with a sleep that advances it keeps the
polling tests instant.
"""

import dataclasses

import pytest
from sharepoint_fakes import (
    LOGIN_URL,
    FakeClock,
    FakeEdge,
    FakePage,
    ok,
    ok_json,
    status,
)

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import (
    FOLDER_URL,
    SITE_URL,
    Limits,
    SharePointClient,
)

SMALL = Limits(
    edge_start_s=0.11, health_ping_s=0.12, request_s=0.13, renewal_s=0.5, sign_in_s=2.0
)


def make_client(edge, limits=SMALL, clock=None):
    clock = clock or FakeClock()
    return SharePointClient(edge, limits=limits, clock=clock, sleep=clock.sleep), clock


# --- ADR-003 constants -------------------------------------------------------------------------------------------


def test_adr003_limit_defaults_match_the_adr():
    limits = Limits()
    assert limits.edge_start_s == 30.0
    assert limits.health_ping_s == 5.0
    assert limits.request_s == 30.0
    assert limits.renewal_s == 45.0
    assert limits.sign_in_s == 180.0


def test_adr003_limits_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Limits().request_s = 1.0


def test_adr002_site_url_is_the_wfr_usteam_site():
    assert SITE_URL == "https://ts.accenture.com/sites/WFR-USTEAM/"
    assert FOLDER_URL.startswith(SITE_URL)
    assert len(FOLDER_URL) > len(SITE_URL)


# --- each limit is used, and a page that never answers gives TimedOut ---------------------------------------------


def test_us07_first_call_starts_headless_edge_on_the_folder_page():
    edge = FakeEdge(FakePage())
    client, _ = make_client(edge)
    client.health_ping()
    assert edge.calls == [(True, FOLDER_URL)]


def test_adr003_health_ping_uses_health_ping_limit():
    page = FakePage()
    client, _ = make_client(FakeEdge(page))
    client.health_ping()
    assert page.timeouts
    assert all(t == SMALL.health_ping_s for _, t in page.timeouts)


def test_adr003_list_and_download_use_request_limit():
    listing = {"value": [], "d": {"results": []}}
    page = FakePage(fetches=[ok_json(listing), ok(b"PK-bytes")])
    client, _ = make_client(FakeEdge(page))
    client.list_files()
    client.download("file-id-1")
    fetch_timeouts = [t for name, t in page.timeouts if name == "evaluate"]
    assert fetch_timeouts == [SMALL.request_s, SMALL.request_s]


@pytest.mark.parametrize(
    ("call", "limit_name"),
    [
        (lambda c: c.health_ping(), "health_ping_s"),
        (lambda c: c.list_files(), "request_s"),
        (lambda c: c.download("file-id-1"), "request_s"),
    ],
    ids=["health_ping", "list_files", "download"],
)
def test_us07_adr003_page_never_answers_raises_timedout_kills_edge_next_call_is_fresh(
    call, limit_name
):
    stuck = FakePage(hang=True)
    fresh = FakePage(
        fetches=[ok_json({"value": [], "d": {"results": []}}), ok(b"PK-bytes")]
    )
    edge = FakeEdge(stuck, fresh)
    client, _ = make_client(edge)

    with pytest.raises(errors.TimedOut):
        call(client)

    assert stuck.timeouts[-1][1] == getattr(SMALL, limit_name)
    assert edge.sessions[0].process.kills >= 1
    assert len(edge.calls) == 1

    call(client)  # the next call starts a fresh Edge instead of reusing the stuck one
    assert edge.calls == [(True, FOLDER_URL), (True, FOLDER_URL)]
    assert edge.sessions[1].page is fresh
    assert edge.sessions[1].process.kills == 0


def test_us07_after_timeout_stuck_page_is_never_used_again():
    stuck = FakePage(hang=True)
    fresh = FakePage()
    edge = FakeEdge(stuck, fresh)
    client, _ = make_client(edge)
    with pytest.raises(errors.TimedOut):
        client.health_ping()
    calls_on_stuck = len(stuck.timeouts)
    client.health_ping()
    client.health_ping()
    assert len(stuck.timeouts) == calls_on_stuck
    assert len(edge.calls) == 2


def test_us07_adr003_renewal_that_never_gets_back_stops_at_renewal_limit():
    page = FakePage(fetches=[status(401)], urls=[LOGIN_URL])
    client, clock = make_client(FakeEdge(page))
    with pytest.raises(errors.NeedsSignIn):
        client.download("file-id-1")
    assert page.navigations == [FOLDER_URL]
    assert SMALL.renewal_s <= clock.t <= SMALL.renewal_s + 1.0


def test_us07_close_kills_the_edge_process():
    edge = FakeEdge(FakePage())
    client, _ = make_client(edge)
    client.health_ping()
    client.close()
    assert edge.sessions[0].process.kills >= 1


# --- US-01 visible sign-in -------------------------------------------------------------------------------------


def test_us01_sign_in_opens_visible_edge_then_switches_to_headless_when_folder_reached():
    visible = FakePage(urls=[LOGIN_URL, LOGIN_URL, FOLDER_URL])
    headless = FakePage()
    edge = FakeEdge(visible, headless)
    client, _ = make_client(edge)

    client.sign_in()

    assert edge.calls == [(False, FOLDER_URL), (True, FOLDER_URL)]
    assert edge.sessions[0].process.kills >= 1
    assert edge.sessions[1].process.kills == 0
    client.health_ping()  # uses the headless session, no third start
    assert len(edge.calls) == 2


def test_us01_adr003_sign_in_not_finished_in_time_kills_visible_edge_and_raises_timedout():
    visible = FakePage(urls=[LOGIN_URL])
    edge = FakeEdge(visible)
    client, clock = make_client(edge)

    with pytest.raises(errors.TimedOut):
        client.sign_in()

    assert edge.calls == [(False, FOLDER_URL)]
    assert edge.sessions[0].process.kills >= 1
    assert SMALL.sign_in_s <= clock.t <= SMALL.sign_in_s + 1.0


def test_us01_default_sign_in_limit_is_three_minutes():
    visible = FakePage(urls=[LOGIN_URL])
    edge = FakeEdge(visible)
    client, clock = make_client(edge, limits=Limits())
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert 180.0 <= clock.t <= 185.0


@pytest.mark.parametrize(
    "not_done_url",
    [
        LOGIN_URL,
        "https://login.microsoftonline.com/x?redirect=https://ts.accenture.com/sites/WFR-USTEAM/",
        "https://ts.accenture.com.evil.com/sites/WFR-USTEAM/",
        "https://example.com/sites/WFR-USTEAM/",
        "https://ts.accenture.com/sites/OTHER-SITE/",
    ],
)
def test_us01_sign_in_is_not_done_on_login_or_foreign_pages(not_done_url):
    edge = FakeEdge(FakePage(urls=[not_done_url]))
    client, _ = make_client(edge)
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert len(edge.calls) == 1


@pytest.mark.parametrize("closed_error", [errors.Unreachable, errors.NotFound])
def test_us01_window_closed_kills_and_reraises_that_error(closed_error):
    visible = FakePage(urls=[LOGIN_URL, closed_error()])
    edge = FakeEdge(visible)
    client, _ = make_client(edge)
    with pytest.raises(closed_error):
        client.sign_in()
    assert edge.calls == [(False, FOLDER_URL)]
    assert edge.sessions[0].process.kills >= 1
