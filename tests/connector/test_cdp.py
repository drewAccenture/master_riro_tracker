"""US-07, ADR-003: the DevTools client never waits longer than its limit.

Fake transports only. Limits are small (0.2 s); every call runs in a daemon thread joined with a timeout, so a
client that hangs fails the test instead of hanging the suite.
"""

import json
import threading
import time

import pytest

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.cdp import CdpClient

LIMIT_S = 0.2
MARGIN_S = 0.5
JOIN_S = 5.0


class SilentTransport:
    """Never answers: recv waits its timeout (capped) and raises the builtin TimeoutError."""

    def __init__(self):
        self.sent = []
        self.recv_timeouts = []

    def send(self, text):
        self.sent.append(text)

    def recv(self, timeout_s):
        self.recv_timeouts.append(timeout_s)
        time.sleep(min(max(timeout_s, 0.0), 1.0))
        raise TimeoutError

    def close(self):
        pass


class EventsOnlyTransport:
    """Answers every recv at once with an unrelated event or a message for another id, forever."""

    def __init__(self):
        self.sent = []
        self.n = 0

    def send(self, text):
        self.sent.append(text)

    def recv(self, timeout_s):
        self.n += 1
        time.sleep(0.005)
        if self.n % 2:
            return json.dumps(
                {"method": "Page.loadEventFired", "params": {"timestamp": self.n}}
            )
        return json.dumps({"id": 999999, "result": {"other": True}})

    def close(self):
        pass


class ScriptedTransport:
    """On send, queues the messages built by `reply(request)`; recv pops them in order."""

    def __init__(self, reply):
        self.reply = reply
        self.sent = []
        self.queue = []

    def send(self, text):
        request = json.loads(text)
        self.sent.append(request)
        self.queue.extend(json.dumps(m) for m in self.reply(request))

    def recv(self, timeout_s):
        if self.queue:
            return self.queue.pop(0)
        time.sleep(min(max(timeout_s, 0.0), 1.0))
        raise TimeoutError

    def close(self):
        pass


def run_bounded(fn):
    """Run fn in a daemon thread. Returns (result, exception, elapsed_s). Fails if it does not end in JOIN_S."""
    box = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - handed back to the test thread
            box["exc"] = exc

    start = time.monotonic()
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=JOIN_S)
    elapsed = time.monotonic() - start
    assert not t.is_alive(), f"CdpClient.call did not return within {JOIN_S} s"
    return box.get("result"), box.get("exc"), elapsed


def test_us07_adr003_no_answer_raises_timedout_within_limit():
    transport = SilentTransport()
    client = CdpClient(transport)
    _, exc, elapsed = run_bounded(
        lambda: client.call("Runtime.evaluate", {}, timeout_s=LIMIT_S)
    )
    assert isinstance(exc, errors.TimedOut)
    assert elapsed < LIMIT_S + MARGIN_S
    assert len(transport.sent) == 1


def test_us07_adr003_unrelated_events_forever_still_time_out_in_total():
    transport = EventsOnlyTransport()
    client = CdpClient(transport)
    _, exc, elapsed = run_bounded(
        lambda: client.call("Runtime.evaluate", {}, timeout_s=LIMIT_S)
    )
    assert isinstance(exc, errors.TimedOut)
    assert elapsed < LIMIT_S + MARGIN_S
    assert transport.n > 1


def test_us07_adr003_limit_is_total_not_per_recv_with_fake_clock():
    """A fake clock that moves 0.1 s per reading: the total limit is hit even though each recv returns at once."""
    ticks = {"t": 0.0}

    def clock():
        ticks["t"] += 0.1
        return ticks["t"]

    transport = EventsOnlyTransport()
    client = CdpClient(transport, clock=clock)
    _, exc, _ = run_bounded(lambda: client.call("Runtime.evaluate", {}, timeout_s=1.0))
    assert isinstance(exc, errors.TimedOut)
    assert transport.n < 50


def test_us07_matching_answer_after_events_returns_result():
    def reply(req):
        return [
            {"method": "Network.requestWillBeSent", "params": {}},
            {"id": req["id"] + 1000, "result": {"wrong": True}},
            {"id": req["id"], "result": {"value": 42}},
        ]

    transport = ScriptedTransport(reply)
    client = CdpClient(transport)
    result, exc, _ = run_bounded(
        lambda: client.call("Runtime.evaluate", {"expression": "1"}, timeout_s=LIMIT_S)
    )
    assert exc is None
    assert result == {"value": 42}
    sent = transport.sent[0]
    assert sent["method"] == "Runtime.evaluate"
    assert sent["params"] == {"expression": "1"}
    assert isinstance(sent["id"], int)
    assert "sessionId" not in sent


def test_us07_session_id_is_sent_when_given():
    transport = ScriptedTransport(lambda req: [{"id": req["id"], "result": {}}])
    client = CdpClient(transport)
    _, exc, _ = run_bounded(
        lambda: client.call(
            "Page.navigate", {"url": "x"}, timeout_s=LIMIT_S, session_id="S1"
        )
    )
    assert exc is None
    assert transport.sent[0]["sessionId"] == "S1"


def test_us07_each_call_uses_a_new_id():
    transport = ScriptedTransport(
        lambda req: [{"id": req["id"], "result": {"id": req["id"]}}]
    )
    client = CdpClient(transport)
    first, _, _ = run_bounded(lambda: client.call("A.a", {}, timeout_s=LIMIT_S))
    second, _, _ = run_bounded(lambda: client.call("B.b", {}, timeout_s=LIMIT_S))
    assert first["id"] != second["id"]
    assert [m["id"] for m in transport.sent] == [first["id"], second["id"]]


def test_us07_error_answer_raises_unreachable():
    def reply(req):
        return [{"id": req["id"], "error": {"code": -32000, "message": "boom"}}]

    client = CdpClient(ScriptedTransport(reply))
    _, exc, _ = run_bounded(
        lambda: client.call("Runtime.evaluate", {}, timeout_s=LIMIT_S)
    )
    assert isinstance(exc, errors.Unreachable)


@pytest.mark.parametrize("limit", [0.05, 0.3])
def test_adr003_recv_is_never_asked_to_wait_past_the_total_limit(limit):
    transport = SilentTransport()
    client = CdpClient(transport)
    run_bounded(lambda: client.call("Runtime.evaluate", {}, timeout_s=limit))
    assert transport.recv_timeouts
    assert all(t <= limit + 1e-6 for t in transport.recv_timeouts)
