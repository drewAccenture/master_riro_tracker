"""Shared fakes for the connector tests. No real Edge; network only on 127.0.0.1.

Helper module (not a test file), imported by the test files in this folder. No test file imports another.
- Client fakes: fake start_edge (FakeEdge), fake page, fake process, fake clock.
- DevTools port fakes (ADR-009): fake Edge process and launcher, fake /json/version server, and the `servers` and
  `hanging_port` fixtures (made available to the tests by conftest.py).
"""

import base64
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import FOLDER_URL, EdgeSession

LOGIN_URL = "https://login.microsoftonline.com/common/oauth2/authorize?client_id=x"


def ok(body: bytes) -> dict:
    return {
        "status": 200,
        "type": "basic",
        "body_b64": base64.b64encode(body).decode("ascii"),
    }


def ok_json(obj) -> dict:
    return ok(json.dumps(obj).encode("utf-8"))


def status(code: int) -> dict:
    return {"status": code, "type": "basic", "body_b64": ""}


REDIRECT = {"status": 0, "type": "opaqueredirect", "body_b64": ""}
NETWORK_ERROR = {"status": 0, "type": "error", "body_b64": ""}


class FakeClock:
    """clock() returns fake time; sleep(s) advances it. Guards against a polling loop that never ends."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = 0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps += 1
        if self.sleeps > 100_000:
            raise AssertionError("polling loop never ended")
        self.t += max(seconds, 0.01)


class FakeProcess:
    def __init__(self):
        self.kills = 0

    def kill(self):
        self.kills += 1


class FakePage:
    """Scripted page.

    fetches: results for evaluate() calls whose expression contains "fetch" (dicts or exceptions), in order.
    Other evaluate() calls (for example a health ping) return True.
    urls: results for current_url(), in order; the last one repeats. Items may be exceptions.
    hang: every call raises TimedOut, as a page that never answers.
    """

    def __init__(self, *, fetches=(), urls=(FOLDER_URL,), hang=False):
        self.fetches = list(fetches)
        self.urls = list(urls)
        self.hang = hang
        self.expressions = []
        self.fetch_expressions = []
        self.timeouts = []
        self.navigations = []

    def evaluate(self, expression, *, timeout_s):
        self.expressions.append(expression)
        self.timeouts.append(("evaluate", timeout_s))
        if self.hang:
            raise errors.TimedOut()
        if "fetch" not in expression:
            return True
        self.fetch_expressions.append(expression)
        if not self.fetches:
            raise AssertionError("unexpected fetch: " + expression[:200])
        result = self.fetches.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def current_url(self, *, timeout_s):
        self.timeouts.append(("current_url", timeout_s))
        if self.hang:
            raise errors.TimedOut()
        result = self.urls.pop(0) if len(self.urls) > 1 else self.urls[0]
        if isinstance(result, BaseException):
            raise result
        return result

    def navigate(self, url, *, timeout_s):
        self.timeouts.append(("navigate", timeout_s))
        self.navigations.append(url)
        if self.hang:
            raise errors.TimedOut()


class FakeEdge:
    """Fake start_edge(headless, url). Hands out the given pages in order, records every start."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = []
        self.sessions = []

    def __call__(self, headless, url):
        self.calls.append((headless, url))
        if not self.pages:
            raise AssertionError("start_edge called more often than the test expected")
        session = EdgeSession(process=FakeProcess(), page=self.pages.pop(0))
        self.sessions.append(session)
        return session


# --- DevTools port fakes (ADR-009) -------------------------------------------------------------------------------


class FakeEdgeProcess:
    """A launched Edge, as start_devtools sees it: its port and how often it was killed."""

    def __init__(self, port: int):
        self.port = port
        self.kills = 0

    def kill(self) -> None:
        self.kills += 1


class FakeLauncher:
    def __init__(self, on_launch=None):
        self.started: list[FakeEdgeProcess] = []
        self.on_launch = on_launch

    def __call__(self, port: int) -> FakeEdgeProcess:
        if self.on_launch:
            self.on_launch(port)
        process = FakeEdgeProcess(port)
        self.started.append(process)
        return process


def edge_answer(port: int) -> dict:
    return {
        "Browser": "Edg/130.0.2849.68",
        "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/browser/abc",
    }


class FakeDevToolsServer:
    """HTTP server on 127.0.0.1. `answer(port)` returns (status, body bytes)."""

    def __init__(self, answer):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.paths.append(self.path)
                status, body = answer(outer.port)
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.paths: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def json_body(data: dict) -> tuple[int, bytes]:
    return 200, json.dumps(data).encode()


def ports(*values):
    return iter(values).__next__


@pytest.fixture
def servers():
    started = []

    def start(answer):
        server = FakeDevToolsServer(answer)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


@pytest.fixture
def hanging_port():
    """Accepts connections at the TCP level and never answers."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    yield sock.getsockname()[1]
    sock.close()


# --- live tests (ADR-011): need -m live AND RIRO_LIVE=1, and a throwaway profile ----------------------------------

LIVE_REASON = "live: needs RIRO_LIVE=1 and -m live"
# A live test file starts with `pytestmark = LIVE`. The string condition is checked when the test runs.
LIVE = [
    pytest.mark.live,
    pytest.mark.skipif('os.environ.get("RIRO_LIVE") != "1"', reason=LIVE_REASON),
]


def assert_throwaway_profile(profile):
    """Refuse the app's data folder and the everyday Edge profile. Returns the path unchanged."""
    path = Path(profile).resolve()
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    for forbidden in (
        local / "RIROTracker",
        local / "Microsoft" / "Edge" / "User Data",
    ):
        assert not path.is_relative_to(forbidden), f"refusing to use {forbidden}"
    return Path(profile)
