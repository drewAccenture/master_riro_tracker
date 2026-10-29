"""ADR-010: Edge gets at most GRACEFUL_CLOSE_S to close politely, then it is killed by its handle.

Fake DevTools connection and fake Edge process: no real Edge.
"""

import time

from riro.connectors.sharepoint import session as session_module
from riro.connectors.sharepoint.cdp import CdpClient
from riro.connectors.sharepoint.edge import _SessionProcess
from riro.connectors.sharepoint.session import EdgeSession, stop

LIMIT_S = 0.3
SLACK_S = 0.2


class SilentDevTools:
    """Edge ignores Browser.close: the command is sent, no answer ever comes."""

    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, text):
        self.sent.append(text)

    def recv(self, timeout_s):
        time.sleep(timeout_s)
        raise TimeoutError

    def close(self):
        self.closed = True


class StubbornEdge:
    """wait() runs out its timeout because Edge never exits by itself."""

    def __init__(self):
        self.kills = 0

    def wait(self, timeout_s):
        time.sleep(timeout_s)

    def kill(self):
        self.kills += 1


def test_adr010_edge_that_ignores_close_is_killed_within_the_limit(monkeypatch):
    monkeypatch.setattr(session_module, "GRACEFUL_CLOSE_S", LIMIT_S)
    devtools, process = SilentDevTools(), StubbornEdge()
    session = EdgeSession(
        process=_SessionProcess(process, devtools, CdpClient(devtools)), page=None
    )

    start = time.monotonic()
    stop(session, graceful=True)
    elapsed = time.monotonic() - start

    assert any(
        '"Browser.close"' in m for m in devtools.sent
    )  # it was asked politely first
    assert process.kills == 1  # then killed by its handle
    assert devtools.closed
    assert elapsed < LIMIT_S + SLACK_S  # the whole polite close stays inside the limit


def test_adr010_kill_without_graceful_never_asks_edge_to_close():
    devtools, process = SilentDevTools(), StubbornEdge()
    session = EdgeSession(
        process=_SessionProcess(process, devtools, CdpClient(devtools)), page=None
    )
    stop(session, graceful=False)
    assert devtools.sent == []
    assert process.kills == 1
