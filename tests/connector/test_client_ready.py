"""US-07, US-08: the page must be a loaded site page before a request runs; Edge started after close() is killed;
a blocked headless Edge after a good sign-in is not reported as a failed sign-in.

NOT_READY is what the fetch JS returns when the page is not (yet) a loaded site page, for example a Microsoft
login page that is about to post back to SharePoint. The reported URL can already be the site then.
"""

import pytest
from sharepoint_fakes import FakeClock, FakeEdge, FakePage, FakeProcess, ok, status

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import (
    FOLDER_URL,
    SITE_URL,
    EdgeSession,
    Limits,
    SharePointClient,
    build_fetch_js,
)

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=20.0, sign_in_s=2.0
)
NOT_READY = {"status": 0, "type": "not_ready", "body_b64": ""}


def make_client(start_edge, limits=SMALL):
    clock = FakeClock()
    return SharePointClient(
        start_edge, limits=limits, clock=clock, sleep=clock.sleep
    ), clock


# --- the fetch runs only from a loaded site page (ADR-002) -------------------------------------------------------


def test_adr002_fetch_js_checks_the_page_before_any_request():
    js = build_fetch_js(SITE_URL + "_api/web")
    assert "location.origin" in js
    assert "document.readyState" in js
    assert '"not_ready"' in js
    assert js.index("not_ready") < js.index("await fetch(")


# --- a page on its way back to the site (US-08 silent renewal) ---------------------------------------------------


def test_us08_page_settling_by_itself_is_waited_for_without_navigating():
    page = FakePage(fetches=[NOT_READY, NOT_READY, ok(b"x")], urls=[FOLDER_URL])
    client, _ = make_client(FakeEdge(page))
    assert client.download("0000-aaaa-1111") == b"x"
    assert page.navigations == []


def test_us08_reported_url_on_site_while_page_is_not_ready_waits_after_renewal():
    page = FakePage(
        fetches=[status(401), NOT_READY, NOT_READY, ok(b"after")], urls=[FOLDER_URL]
    )
    client, _ = make_client(FakeEdge(page))
    assert client.download("0000-aaaa-1111") == b"after"
    assert page.navigations == [FOLDER_URL]


def test_us08_page_never_ready_renews_once_then_needs_sign_in_within_the_limit():
    page = FakePage(fetches=[NOT_READY] * 500, urls=[FOLDER_URL])
    client, clock = make_client(FakeEdge(page))
    with pytest.raises(errors.NeedsSignIn):
        client.list_files()
    assert page.navigations == [FOLDER_URL]
    assert clock.t <= SMALL.renewal_s + 1.0


# --- close() during an Edge start (watchdog, ADR-003) --------------------------------------------------------------


class AbortableStart:
    """Fake start_edge with abort(), like the real factory. Calls `during` while starting."""

    def __init__(self, during=None):
        self.during = during
        self.aborts = 0
        self.sessions = []

    def abort(self):
        self.aborts += 1

    def __call__(self, headless, url):
        session = EdgeSession(process=FakeProcess(), page=FakePage())
        self.sessions.append(session)
        if self.during:
            self.during()
        return session


def test_adr003_close_stops_an_edge_that_is_still_starting():
    start = AbortableStart()
    client, _ = make_client(start)
    start.during = client.close  # the watchdog fires while Edge starts
    with pytest.raises(errors.TimedOut):
        client.health_ping()
    assert start.aborts >= 1
    assert start.sessions[0].process.kills >= 1
    start.during = None
    client.health_ping()  # the next call starts a fresh Edge and keeps it
    assert start.sessions[1].process.kills == 0


def test_adr002_shutdown_also_stops_an_edge_that_is_starting():
    start = AbortableStart()
    client, _ = make_client(start)
    client.shutdown()
    assert start.aborts >= 1


# --- good sign-in, blocked headless Edge (US-01, plan risk 1) -------------------------------------------------------


def test_us01_headless_blocked_after_good_sign_in_is_not_a_failed_sign_in():
    visible = FakePage(urls=[FOLDER_URL])
    calls = []

    def start_edge(headless, url):
        calls.append(headless)
        if headless:
            raise errors.EdgeNotStarted("Edge could not be started")
        return EdgeSession(process=FakeProcess(), page=visible)

    client, _ = make_client(start_edge)
    client.sign_in()  # the sign-in itself worked
    with pytest.raises(errors.EdgeNotStarted):
        client.health_ping()  # the real reason comes from the next call
    assert calls == [False, True, True]
