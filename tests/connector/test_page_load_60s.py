"""Slice 8b, ADR-014 (tunes ADR-003), US-06, US-07: the hidden Edge's first page load may take up to 60 s.

- A headless start whose page loads after 45 s succeeds; one that never loads ends at 60 s and Edge is killed.
- One headless start is at most DEVTOOLS_START_LIMIT_S + 60 s.
- A visible start still waits VISIBLE_PAGE_S (180 s).
- A whole sync with a page that never loads still ends within services.sync.SYNC_LIMIT_S (3 minutes).

Fake Edge, fake DevTools connection and a fake clock (sleep advances it), so the tests are fast.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from sharepoint_fakes import FakeClock

from riro.connectors.sharepoint import edge, errors
from riro.connectors.sharepoint.client import SharePointClient
from riro.services.diagnostics import Diagnostics
from riro.services.sync import MESSAGES, SYNC_LIMIT_S, SyncService

URL = "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Forms/AllItems.aspx"
WS = "ws://127.0.0.1:9333/devtools/browser/x"
NOW = datetime(2026, 11, 3, 9, 30, 0)


class FakeProcess:
    def __init__(self):
        self.kills = 0

    def kill(self):
        self.kills += 1

    def wait(self, timeout_s):
        return True


class FakeDevTools:
    """Fake transport. readiness: document.readyState answers in turn; the last one repeats."""

    def __init__(self, *readiness):
        self.readiness = list(readiness) or ["complete"]
        self.queue = []
        self.closed = False

    def send(self, text):
        request = json.loads(text)
        method = request["method"]
        if method == "Runtime.evaluate":
            state = (
                self.readiness.pop(0) if len(self.readiness) > 1 else self.readiness[0]
            )
            answer = {"result": {"type": "string", "value": state}}
        else:
            answer = {
                "Browser.getVersion": {"product": "Edg/999.0.1"},
                "Target.createTarget": {"targetId": "T1"},
                "Target.attachToTarget": {"sessionId": "S1"},
                "Page.navigate": {"frameId": "F1", "loaderId": "L1"},
                "Browser.close": {},
            }[method]
        self.queue.append(json.dumps({"id": request["id"], "result": answer}))

    def recv(self, timeout_s):
        if self.queue:
            return self.queue.pop(0)
        raise TimeoutError

    def close(self):
        self.closed = True


class Started:
    """A start_edge with the module defaults (no page_s / visible_page_s passed), a fake clock and fake Edge.

    devtools_s: fake seconds Edge takes until DevTools answers. make_devtools: a new fake connection per start.
    """

    def __init__(self, make_devtools, *, devtools_s=0.0, poll_s=1.0):
        self.clock = FakeClock()
        self.processes = []
        self.connections = []
        self.events = []

        def launch(exe, profile_dir, port, *, headless, url):
            self.processes.append(FakeProcess())
            return self.processes[-1]

        def start(launch_on_port, **kwargs):
            self.clock.t += devtools_s
            return launch_on_port(9333), WS

        def connect(ws_url, timeout_s):
            self.connections.append(make_devtools())
            return self.connections[-1]

        self.start_edge = edge.make_start_edge(
            Path("edge_profile"),
            on_event=lambda step, **fields: self.events.append((step, fields)),
            find=lambda: Path("msedge.exe"),
            launch=launch,
            start=start,
            connect=connect,
            poll_s=poll_s,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

    def kills(self):
        return sum(p.kills for p in self.processes)

    def page_loads(self):
        return [fields for step, fields in self.events if step == "page_load"]


def loading_then_complete(seconds):
    """With polls of 1 s: "loading" for about `seconds` fake seconds, then "complete"."""
    return ["loading"] * int(seconds) + ["complete"]


# --- the numbers ------------------------------------------------------------------------------------------------


def test_adr014_hidden_page_load_limit_is_60_s():
    assert edge.PAGE_S == 60.0


def test_adr014_one_headless_start_is_devtools_limit_plus_60_s():
    assert edge.START_TOTAL_S == edge.DEVTOOLS_START_LIMIT_S + 60.0


def test_adr014_other_adr003_limits_are_unchanged():
    assert edge.DEVTOOLS_START_LIMIT_S == 30.0
    assert edge.VISIBLE_PAGE_S == 180.0
    assert SYNC_LIMIT_S == 180.0


# --- headless start ---------------------------------------------------------------------------------------------


def test_adr014_headless_page_that_loads_after_45_s_succeeds():
    run = Started(lambda: FakeDevTools(*loading_then_complete(45)))
    session = run.start_edge(True, URL)
    assert session.page is not None
    assert run.kills() == 0
    assert 45.0 <= run.clock.t < 50.0
    [fields] = run.page_loads()
    assert fields["result"] == "ok"
    assert 45.0 <= fields["duration_s"] < 50.0


def test_adr014_headless_page_that_never_loads_ends_at_60_s_and_kills_edge():
    run = Started(lambda: FakeDevTools("loading"))
    with pytest.raises(errors.TimedOut):
        run.start_edge(True, URL)
    assert run.kills() >= 1
    assert run.connections[0].closed
    assert 60.0 <= run.clock.t < 61.0
    [fields] = run.page_loads()
    assert (fields["result"], fields["error_kind"]) == ("failed", "TimedOut")


def test_adr014_headless_start_with_slow_devtools_ends_by_devtools_limit_plus_60_s():
    run = Started(
        lambda: FakeDevTools("loading"), devtools_s=edge.DEVTOOLS_START_LIMIT_S
    )
    with pytest.raises(errors.TimedOut):
        run.start_edge(True, URL)
    assert run.kills() >= 1
    limit = edge.DEVTOOLS_START_LIMIT_S + 60.0
    assert limit - 1.0 <= run.clock.t <= limit + 1.0


# --- visible start: unchanged -----------------------------------------------------------------------------------


def test_us01_visible_page_that_loads_after_120_s_still_succeeds():
    run = Started(lambda: FakeDevTools(*loading_then_complete(120)))
    session = run.start_edge(False, URL)
    assert session.page is not None
    assert run.kills() == 0
    assert 120.0 <= run.clock.t < 125.0


def test_us01_visible_page_that_never_loads_still_ends_at_180_s():
    run = Started(lambda: FakeDevTools("loading"))
    with pytest.raises(errors.TimedOut):
        run.start_edge(False, URL)
    assert run.kills() >= 1
    assert 180.0 <= run.clock.t < 181.0


# --- whole sync -------------------------------------------------------------------------------------------------


def test_adr014_whole_sync_with_a_page_that_never_loads_ends_within_the_sync_limit():
    # Worst case: every Edge start uses the whole DevTools limit, then the whole page limit. The sync's own
    # retry (ADR-003: TimedOut on the ping -> one fresh Edge) makes two starts; together they stay inside 3 min.
    run = Started(
        lambda: FakeDevTools("loading"), devtools_s=edge.DEVTOOLS_START_LIMIT_S
    )
    client = SharePointClient(run.start_edge, clock=run.clock, sleep=run.clock.sleep)
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    service = SyncService(client, diagnostics, clock=run.clock, now=lambda: NOW)

    result = service.sync()

    assert result.state == "failed"
    assert result.message == MESSAGES["TimedOut"]
    assert run.clock.t <= SYNC_LIMIT_S + 1.0
    assert len(run.processes) == 2  # the first start and the sync's one retry, no more
    assert all(p.kills >= 1 for p in run.processes)
    # Each start really waited the 60 s page limit (with 30 s it would end at 120 s).
    assert run.clock.t >= 2 * (edge.DEVTOOLS_START_LIMIT_S + 60.0) - 1.0
