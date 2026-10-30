"""Slice 7b review fixes (ADR-003: visible sign-in at most 3 minutes, US-01, ADR-010).

- The visible start's own deadline includes the DevTools start, so it never runs past visible_page_s.
- A sign-in whose slow start returns on a site page right at the deadline still gets its second poll.
- An abort (app exit) ends a long visible page wait at once.
- A sign-in asked for after app exit started does not open Edge.
"""

import json
from pathlib import Path

import pytest
from sharepoint_fakes import FakeClock, FakePage, FakeProcess

from riro.connectors.sharepoint import edge, errors
from riro.connectors.sharepoint.client import FOLDER_URL, Limits, SharePointClient
from riro.connectors.sharepoint.session import EdgeSession

URL = "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Forms/AllItems.aspx"
LOGIN = "https://login.microsoftonline.com/common/oauth2/authorize"
WS = "ws://127.0.0.1:9333/devtools/browser/x"
SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=1.0, sign_in_s=2.0
)


class LoadingDevTools:
    """A DevTools connection whose page never finishes loading."""

    def __init__(self):
        self.queue = []
        self.closed = False

    def send(self, text):
        request = json.loads(text)
        answers = {
            "Browser.getVersion": {"product": "Edg/999.0.1"},
            "Target.createTarget": {"targetId": "T1"},
            "Target.attachToTarget": {"sessionId": "S1"},
            "Page.navigate": {"frameId": "F1", "loaderId": "L1"},
            "Runtime.evaluate": {"result": {"type": "string", "value": "loading"}},
        }
        self.queue.append(
            json.dumps({"id": request["id"], "result": answers[request["method"]]})
        )

    def recv(self, timeout_s):
        if self.queue:
            return self.queue.pop(0)
        raise TimeoutError

    def close(self):
        self.closed = True


def starter(clock, *, devtools_s=0.0, sleep=None, **options):
    process = FakeProcess()

    def start(launch_on_port, **kwargs):
        clock.t += devtools_s  # time Edge took until DevTools answered
        return launch_on_port(9333), WS

    start_edge = edge.make_start_edge(
        Path("edge_profile"),
        find=lambda: Path("msedge.exe"),
        launch=lambda exe, profile_dir, port, *, headless, url: process,
        start=start,
        connect=lambda ws_url, timeout_s: LoadingDevTools(),
        poll_s=1.0,
        clock=clock,
        sleep=sleep or clock.sleep,
        **options,
    )
    return start_edge, process


def test_adr003_visible_start_with_a_slow_devtools_start_still_ends_by_visible_page_s():
    clock = FakeClock()
    start_edge, process = starter(clock, devtools_s=25.0)
    with pytest.raises(errors.TimedOut):
        start_edge(False, URL)
    assert clock.t <= edge.VISIBLE_PAGE_S + 1.0
    assert process.kills >= 1


def test_adr003_headless_start_keeps_its_devtools_plus_page_deadline():
    clock = FakeClock()
    start_edge, _ = starter(clock, devtools_s=25.0)
    with pytest.raises(errors.TimedOut):
        start_edge(True, URL)
    assert (
        edge.PAGE_S + 25.0 <= clock.t <= edge.DEVTOOLS_START_LIMIT_S + edge.PAGE_S + 1
    )


def test_adr010_abort_during_a_visible_page_wait_ends_it_at_once():
    clock = FakeClock()
    holder = []

    def sleep(seconds):
        clock.sleep(seconds)
        if clock.t >= 3.0:
            holder[0].abort()  # app exit while she is still on the first page

    start_edge, process = starter(clock, sleep=sleep)
    holder.append(start_edge)
    with pytest.raises(errors.TimedOut):
        start_edge(False, URL)
    assert clock.t < 10.0  # not the whole 180 s
    assert process.kills >= 1


class SlowStart:
    """start_edge(headless, url) that takes the given fake seconds, then returns a page on the given URLs."""

    def __init__(self, clock, takes_s, urls):
        self.clock, self.takes_s, self.urls = clock, takes_s, urls
        self.calls = []

    def __call__(self, headless, url):
        self.calls.append(headless)
        self.clock.t += self.takes_s
        return EdgeSession(process=FakeProcess(), page=FakePage(urls=self.urls))


def make_client(start_edge, clock):
    events = []
    client = SharePointClient(
        start_edge,
        limits=SMALL,
        clock=clock,
        sleep=clock.sleep,
        on_event=lambda step, **fields: events.append((step, fields)),
    )
    return client, events


def test_us01_start_that_returns_on_a_site_page_at_the_deadline_is_a_finished_sign_in():
    clock = FakeClock()
    start = SlowStart(clock, takes_s=SMALL.sign_in_s, urls=[FOLDER_URL])
    client, events = make_client(start, clock)
    client.sign_in()
    assert [f["result"] for s, f in events if s == "sign_in"] == ["ok"]


def test_us01_start_that_returns_on_a_login_page_at_the_deadline_did_not_finish():
    clock = FakeClock()
    client, events = make_client(
        SlowStart(clock, takes_s=SMALL.sign_in_s, urls=[LOGIN]), clock
    )
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert [f["result"] for s, f in events if s == "sign_in"] == ["failed"]


def test_adr010_sign_in_after_app_exit_started_never_opens_edge():
    clock = FakeClock()
    start = SlowStart(clock, takes_s=0.0, urls=[FOLDER_URL])
    client, _ = make_client(start, clock)
    client.shutdown()
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert start.calls == []
