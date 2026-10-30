"""Slice 7b, US-01, ADR-003: a visible sign-in start waits up to visible_page_s (3 min) for its first page; a headless
start keeps page_s (30 s). US-16: every start writes one page_load event (ok, or failed TimedOut / Unreachable).

Fake Edge, fake DevTools connection and a fake clock (sleep advances it), so the tests are fast.
"""

import json
from pathlib import Path

import pytest
from sharepoint_fakes import FakeClock

from riro.connectors.sharepoint import edge, errors

URL = "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Forms/AllItems.aspx"
WS = "ws://127.0.0.1:9333/devtools/browser/x"


class FakeProcess:
    def __init__(self):
        self.kills = 0

    def kill(self):
        self.kills += 1

    def wait(self, timeout_s):
        return True


class FakeDevTools:
    """Fake transport. answers: method -> result dict, or a list used in turn (the last one repeats)."""

    def __init__(self, **answers):
        self.answers = {
            "Browser.getVersion": {"product": "Edg/999.0.1"},
            "Target.createTarget": {"targetId": "T1"},
            "Target.attachToTarget": {"sessionId": "S1"},
            "Page.navigate": {"frameId": "F1", "loaderId": "L1"},
            "Runtime.evaluate": {"result": {"type": "string", "value": "complete"}},
            "Browser.close": {},
        }
        self.answers.update({k.replace("_", "."): v for k, v in answers.items()})
        self.sent = []
        self.queue = []
        self.closed = False

    def send(self, text):
        request = json.loads(text)
        self.sent.append(request)
        answer = self.answers[request["method"]]
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        self.queue.append(json.dumps({"id": request["id"], "result": answer}))

    def recv(self, timeout_s):
        if self.queue:
            return self.queue.pop(0)
        raise TimeoutError

    def close(self):
        self.closed = True


def readiness(*states):
    return [{"result": {"type": "string", "value": s}} for s in states]


def slow_page(polls_loading):
    return readiness(*(["loading"] * polls_loading), "complete")


class Started:
    """One start_edge plus what it did: the fake process, the fake clock and the events it wrote."""

    def __init__(self, devtools, *, poll_s=0.01, **options):
        self.process = FakeProcess()
        self.clock = FakeClock()
        self.events = []
        self.devtools = devtools

        def start(launch_on_port, **kwargs):
            return launch_on_port(9333), WS

        self.start_edge = edge.make_start_edge(
            Path("edge_profile"),
            on_event=lambda step, **fields: self.events.append((step, fields)),
            find=lambda: Path("msedge.exe"),
            launch=lambda exe, profile_dir, port, *, headless, url: self.process,
            start=start,
            connect=lambda ws_url, timeout_s: devtools,
            poll_s=poll_s,
            clock=self.clock,
            sleep=self.clock.sleep,
            **options,
        )

    def page_loads(self):
        return [fields for step, fields in self.events if step == "page_load"]


# --- visible_page_s ---------------------------------------------------------------------------------------------


def test_adr003_visible_page_limit_is_the_three_minute_sign_in_limit():
    assert edge.VISIBLE_PAGE_S == 180.0


def test_us01_visible_start_waits_past_page_s_for_a_slow_first_page():
    # About 0.3 s of "loading" (30 polls of 0.01 s): more than page_s, well inside visible_page_s.
    run = Started(
        FakeDevTools(Runtime_evaluate=slow_page(30)), page_s=0.2, visible_page_s=2.0
    )
    session = run.start_edge(False, URL)
    assert session.page is not None
    assert run.process.kills == 0
    assert run.clock.t > 0.2


def test_adr003_headless_start_with_the_same_slow_page_still_times_out_at_page_s():
    run = Started(
        FakeDevTools(Runtime_evaluate=slow_page(30)), page_s=0.2, visible_page_s=2.0
    )
    with pytest.raises(errors.TimedOut):
        run.start_edge(True, URL)
    assert run.process.kills >= 1
    assert run.devtools.closed
    assert run.clock.t < 0.3  # it gave up at page_s, not at visible_page_s


def test_us01_visible_page_that_never_loads_times_out_at_visible_page_s_and_kills_edge():
    run = Started(
        FakeDevTools(Runtime_evaluate=readiness("loading")),
        page_s=0.2,
        visible_page_s=2.0,
    )
    with pytest.raises(errors.TimedOut):
        run.start_edge(False, URL)
    assert run.process.kills >= 1
    assert run.devtools.closed
    assert 2.0 <= run.clock.t < 2.5


def test_us01_default_visible_start_waits_the_full_180_s_for_the_page():
    # Defaults only (no page_s or visible_page_s passed); polls of 1 s keep the fake run short.
    run = Started(FakeDevTools(Runtime_evaluate=readiness("loading")), poll_s=1.0)
    with pytest.raises(errors.TimedOut):
        run.start_edge(False, URL)
    assert run.process.kills >= 1
    assert 180.0 <= run.clock.t < 185.0


def test_adr003_default_headless_start_still_waits_only_30_s_for_the_page():
    run = Started(FakeDevTools(Runtime_evaluate=readiness("loading")), poll_s=1.0)
    with pytest.raises(errors.TimedOut):
        run.start_edge(True, URL)
    assert run.process.kills >= 1
    assert 30.0 <= run.clock.t < 35.0


# --- page_load event (US-16) -----------------------------------------------------------------------------------


def test_us16_successful_start_writes_one_page_load_ok_with_duration():
    run = Started(FakeDevTools(Runtime_evaluate=slow_page(5)), page_s=0.5)
    run.start_edge(True, URL)
    [fields] = run.page_loads()
    assert set(fields) == {"result", "duration_s"}
    assert fields["result"] == "ok"
    assert isinstance(fields["duration_s"], float)
    assert 0.0 <= fields["duration_s"] <= 0.5


def test_us16_successful_visible_start_writes_one_page_load_ok():
    run = Started(
        FakeDevTools(Runtime_evaluate=slow_page(30)), page_s=0.2, visible_page_s=2.0
    )
    run.start_edge(False, URL)
    [fields] = run.page_loads()
    assert fields["result"] == "ok"
    assert (
        fields["duration_s"] > 0.2
    )  # the slow page's time, measured from Page.navigate


def test_us16_page_that_never_loads_writes_page_load_failed_timed_out():
    run = Started(FakeDevTools(Runtime_evaluate=readiness("loading")), page_s=0.2)
    with pytest.raises(errors.TimedOut):
        run.start_edge(True, URL)
    [fields] = run.page_loads()
    assert set(fields) == {"result", "error_kind", "duration_s"}
    assert fields["result"] == "failed"
    assert fields["error_kind"] == "TimedOut"
    assert isinstance(fields["duration_s"], float)
    assert fields["duration_s"] >= 0.2


def test_us16_navigation_error_writes_page_load_failed_unreachable():
    run = Started(
        FakeDevTools(
            Page_navigate={"frameId": "F1", "errorText": "net::ERR_NAME_NOT_RESOLVED"}
        )
    )
    with pytest.raises(errors.Unreachable):
        run.start_edge(True, URL)
    assert run.process.kills >= 1
    [fields] = run.page_loads()
    assert set(fields) == {"result", "error_kind", "duration_s"}
    assert fields["result"] == "failed"
    assert fields["error_kind"] == "Unreachable"
    assert isinstance(fields["duration_s"], float)


def test_us16_two_starts_write_one_page_load_each():
    run = Started(FakeDevTools())
    run.start_edge(True, URL)
    run.start_edge(False, URL)
    assert [f["result"] for f in run.page_loads()] == ["ok", "ok"]


def test_adr007_page_load_event_carries_no_url_and_no_headless_flag():
    run = Started(FakeDevTools())
    run.start_edge(False, URL)
    for step, fields in run.events:
        assert URL not in [str(v) for v in fields.values()]
        if step == "page_load":
            assert "url" not in fields
            assert "headless" not in fields
