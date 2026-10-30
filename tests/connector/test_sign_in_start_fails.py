"""Slice 7b, US-01, US-08: a visible sign-in whose Edge start itself fails still writes the connector's
"sign_in result=failed duration_s=..." line before the error reaches the service. A sign-in that works writes
"sign_in result=ok duration_s=..." once.
"""

import pytest
from sharepoint_fakes import FakeClock, FakeEdge, FakePage

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import FOLDER_URL, Limits, SharePointClient

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=1.0, sign_in_s=2.0
)


class FailingStart:
    """start_edge(headless, url) that raises the given error, after the given fake seconds."""

    def __init__(self, error, clock, takes_s=1.5):
        self.error, self.clock, self.takes_s = error, clock, takes_s
        self.calls = []

    def __call__(self, headless, url):
        self.calls.append((headless, url))
        self.clock.t += self.takes_s
        raise self.error


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


def sign_ins(events):
    return [fields for step, fields in events if step == "sign_in"]


@pytest.mark.parametrize(
    "error",
    [errors.TimedOut("page did not finish loading"), errors.EdgeNotStarted("no")],
    ids=["TimedOut", "EdgeNotStarted"],
)
def test_us08_failed_edge_start_writes_one_failed_sign_in_with_duration(error):
    clock = FakeClock()
    start = FailingStart(error, clock)
    client, events = make_client(start, clock)
    with pytest.raises(type(error)):
        client.sign_in()
    assert start.calls == [(False, FOLDER_URL)]
    [fields] = sign_ins(events)
    assert fields["result"] == "failed"
    assert isinstance(fields["duration_s"], float)
    assert fields["duration_s"] == pytest.approx(1.5)


def test_us08_failed_edge_start_error_is_the_one_the_start_raised():
    clock = FakeClock()
    error = errors.TimedOut("page did not finish loading")
    client, _ = make_client(FailingStart(error, clock), clock)
    with pytest.raises(errors.TimedOut) as raised:
        client.sign_in()
    assert raised.value is error


def test_us08_failed_edge_start_leaves_no_visible_session_behind():
    # After the failed start a normal headless call starts a fresh headless Edge (nothing visible is kept).
    clock = FakeClock()
    calls = []
    pages = FakeEdge(FakePage())

    def start_edge(headless, url):
        calls.append(headless)
        if not headless:
            raise errors.TimedOut("page did not finish loading")
        return pages(headless, url)

    client, _ = make_client(start_edge, clock)
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    client.health_ping()
    assert calls == [False, True]


def test_us08_successful_sign_in_still_writes_one_ok_line_with_duration():
    clock = FakeClock()
    edges = FakeEdge(FakePage(urls=[FOLDER_URL]), FakePage())
    client, events = make_client(edges, clock)
    client.sign_in()
    [fields] = sign_ins(events)
    assert fields["result"] == "ok"
    assert isinstance(fields["duration_s"], float)
