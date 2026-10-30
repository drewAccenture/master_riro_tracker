"""US-01, US-07, US-08: SharePoint's own sign-in pages, a lost Edge, closing at once vs. on app exit."""

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
    EdgeSession,
    Limits,
    SharePointClient,
)

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=2.0, sign_in_s=2.0
)
SIGN_IN_HOPS = [
    SITE_URL + "_layouts/15/Authenticate.aspx?Source=%2Fsites%2FWFR-USTEAM",
    SITE_URL + "_LAYOUTS/15/start.aspx",
    SITE_URL + "_forms/default.aspx?ReturnUrl=x",
    SITE_URL + "_trust/default.aspx",
    SITE_URL + "_login/default.aspx",
]


def make_client(start_edge):
    clock = FakeClock()
    return SharePointClient(start_edge, limits=SMALL, clock=clock, sleep=clock.sleep)


class LostPage(FakePage):
    """Edge died: every DevTools call fails because the connection is gone."""

    def evaluate(self, expression, *, timeout_s):
        self.expressions.append(expression)
        raise errors.Unreachable("DevTools connection lost")


class GracefulProcess:
    def __init__(self):
        self.closes = []
        self.kills = 0

    def close(self, timeout_s):
        self.closes.append(timeout_s)

    def kill(self):
        self.kills += 1


# --- a lost Edge is replaced (US-07 "the next sync starts clean") ----------------------------------------------


def test_us07_lost_connection_on_ping_drops_session_next_call_is_fresh():
    edge = FakeEdge(LostPage(), FakePage())
    client = make_client(edge)
    with pytest.raises(errors.Unreachable):
        client.health_ping()
    assert edge.sessions[0].process.kills >= 1
    client.health_ping()
    assert len(edge.calls) == 2
    assert edge.sessions[1].process.kills == 0


def test_us07_lost_connection_on_list_drops_session_next_call_is_fresh():
    dead = FakePage(fetches=[errors.Unreachable("DevTools connection lost")])
    edge = FakeEdge(dead, FakePage(fetches=[ok_json({"value": []})]))
    client = make_client(edge)
    with pytest.raises(errors.Unreachable):
        client.list_files()
    assert edge.sessions[0].process.kills >= 1
    assert client.list_files() == []
    assert len(edge.calls) == 2


# --- SharePoint's own sign-in pages are not "signed in" (US-01, US-08) ------------------------------------------


@pytest.mark.parametrize("hop", SIGN_IN_HOPS)
def test_us01_sharepoint_sign_in_pages_do_not_count_as_signed_in(hop):
    edge = FakeEdge(FakePage(urls=[hop]))
    client = make_client(edge)
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert len(edge.calls) == 1


@pytest.mark.parametrize("hop", SIGN_IN_HOPS)
def test_us08_renewal_waits_past_sharepoint_sign_in_pages(hop):
    page = FakePage(fetches=[status(401), ok(b"after")], urls=[hop, hop, FOLDER_URL])
    client = make_client(FakeEdge(page))
    assert client.download("0000-aaaa-1111") == b"after"
    assert len(page.fetch_expressions) == 2


@pytest.mark.parametrize("hop", SIGN_IN_HOPS)
def test_us08_renewal_stuck_on_sharepoint_sign_in_page_needs_sign_in(hop):
    page = FakePage(fetches=[status(401)], urls=[hop])
    client = make_client(FakeEdge(page))
    with pytest.raises(errors.NeedsSignIn):
        client.download("0000-aaaa-1111")
    assert len(page.fetch_expressions) == 1


# --- close() kills at once (ADR-003), shutdown() closes politely on app exit ------------------------------------


def one_session(process):
    def start_edge(headless, url):
        return EdgeSession(process=process, page=FakePage())

    return start_edge


def test_adr003_close_kills_at_once_without_graceful_close():
    process = GracefulProcess()
    client = make_client(one_session(process))
    client.health_ping()
    client.close()
    assert process.closes == []
    assert process.kills >= 1


def test_adr002_shutdown_closes_gracefully_then_kills():
    process = GracefulProcess()
    client = make_client(one_session(process))
    client.health_ping()
    client.shutdown()
    assert len(process.closes) == 1
    assert process.kills >= 1


def test_us01_app_closed_during_sign_in_kills_visible_edge_and_starts_no_headless():
    holder = {}

    class ClosingPage(FakePage):
        def current_url(self, *, timeout_s):
            holder["client"].shutdown()  # the app window is closed while she signs in
            return LOGIN_URL

    edge = FakeEdge(ClosingPage())
    client = make_client(edge)
    holder["client"] = client
    with pytest.raises(errors.ConnectorError):
        client.sign_in()
    assert edge.sessions[0].process.kills >= 1
    assert edge.calls == [(False, FOLDER_URL)]
