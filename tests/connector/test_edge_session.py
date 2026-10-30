"""ADR-002, ADR-003, ADR-009, US-07: the real start_edge factory with a fake Edge, port and DevTools connection.

Edge starts on about:blank; our own tab is then sent to the URL and the page must finish loading before it is used.
Any failure on the way kills Edge.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from riro.connectors.sharepoint import edge, errors

URL = "https://ts.accenture.com/sites/WFR-USTEAM/Shared%20Documents/Forms/AllItems.aspx"
WS = "ws://127.0.0.1:9333/devtools/browser/x"


class FakeProcess:
    def __init__(self):
        self.kills = 0
        self.waits = []

    def kill(self):
        self.kills += 1

    def wait(self, timeout_s):
        self.waits.append(timeout_s)


class FakeDevTools:
    """Fake transport. answers: method -> result dict, or a list of results used in turn (last one repeats)."""

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

    def methods(self):
        return [m["method"] for m in self.sent]


def readiness(*states):
    return [{"result": {"type": "string", "value": s}} for s in states]


def factory(devtools, *, connect=None, page_s=0.5, versions=None):
    launched = []
    process = FakeProcess()

    def launch(exe, profile_dir, port, *, headless, url):
        launched.append({"exe": exe, "port": port, "headless": headless, "url": url})
        return process

    def start(launch_on_port, **kwargs):
        return launch_on_port(9333), WS

    start_edge = edge.make_start_edge(
        Path("edge_profile"),
        on_version=versions.append if versions is not None else None,
        find=lambda: Path("msedge.exe"),
        launch=launch,
        start=start,
        connect=connect or (lambda ws_url, timeout_s: devtools),
        page_s=page_s,
        poll_s=0.01,
    )
    return start_edge, launched, process


def test_adr009_edge_starts_blank_then_our_own_tab_loads_the_url():
    devtools = FakeDevTools()
    versions = []
    start_edge, launched, process = factory(devtools, versions=versions)

    session = start_edge(True, URL)

    assert launched == [
        {
            "exe": Path("msedge.exe"),
            "port": 9333,
            "headless": True,
            "url": "about:blank",
        }
    ]
    assert versions == ["Edg/999.0.1"]
    methods = devtools.methods()
    assert methods.index("Target.createTarget") < methods.index("Page.navigate")
    navigate = next(m for m in devtools.sent if m["method"] == "Page.navigate")
    assert navigate["params"] == {"url": URL}
    assert navigate["sessionId"] == "S1"
    assert methods[-1] == "Runtime.evaluate"
    assert process.kills == 0
    assert session.page is not None


def test_us07_page_still_loading_is_waited_for():
    devtools = FakeDevTools(
        Runtime_evaluate=readiness("loading", "interactive", "complete")
    )
    start_edge, _, process = factory(devtools)
    start_edge(True, URL)
    assert devtools.methods().count("Runtime.evaluate") == 3
    assert process.kills == 0


def test_adr003_page_never_finishes_loading_kills_edge_and_times_out():
    devtools = FakeDevTools(Runtime_evaluate=readiness("loading"))
    start_edge, _, process = factory(devtools, page_s=0.2)
    with pytest.raises(errors.TimedOut):
        start_edge(True, URL)
    assert process.kills >= 1
    assert devtools.closed


def test_us07_navigation_error_kills_edge():
    devtools = FakeDevTools(
        Page_navigate={"frameId": "F1", "errorText": "net::ERR_NAME_NOT_RESOLVED"}
    )
    start_edge, _, process = factory(devtools)
    with pytest.raises(errors.Unreachable):
        start_edge(True, URL)
    assert process.kills >= 1


def test_us07_attach_answer_without_session_id_kills_edge():
    devtools = FakeDevTools(Target_attachToTarget={})
    start_edge, _, process = factory(devtools)
    with pytest.raises(errors.Unreachable):
        start_edge(False, URL)
    assert process.kills >= 1


def test_us07_websocket_failure_kills_edge():
    def connect(ws_url, timeout_s):
        raise errors.Unreachable("DevTools connection failed")

    start_edge, _, process = factory(FakeDevTools(), connect=connect)
    with pytest.raises(errors.Unreachable):
        start_edge(True, URL)
    assert process.kills >= 1


def test_adr002_graceful_close_asks_edge_to_close_then_waits():
    devtools = FakeDevTools()
    start_edge, _, process = factory(devtools)
    session = start_edge(True, URL)
    session.process.close(1.5)
    assert devtools.methods()[-1] == "Browser.close"
    # ADR-010: asking and waiting share one limit, so the wait gets what is left of it.
    assert len(process.waits) == 1
    assert 1.0 <= process.waits[0] <= 1.5
    session.process.kill()
    assert process.kills >= 1
    assert devtools.closed


# --- ADR-009: a program on the port that does not speak HTTP counts as "port not ours" ---------------------------


def test_adr009_non_http_answer_counts_as_not_ours():
    garbage = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    garbage.bind(("127.0.0.1", 0))
    garbage.listen(4)

    def answer_garbage():
        try:
            conn, _ = garbage.accept()
            conn.recv(1024)
            conn.sendall(b"HELLO NOT HTTP\r\n\r\n")
            conn.close()
        except OSError:
            pass

    class Ours(BaseHTTPRequestHandler):
        def do_GET(self):
            port = self.server.server_address[1]
            body = json.dumps(
                {
                    "Browser": "Edg/1.0",
                    "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/browser/a",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    ours = ThreadingHTTPServer(("127.0.0.1", 0), Ours)
    threads = [
        threading.Thread(target=answer_garbage, daemon=True),
        threading.Thread(target=ours.serve_forever, daemon=True),
    ]
    for t in threads:
        t.start()
    garbage_port, ours_port = garbage.getsockname()[1], ours.server_address[1]
    ports = iter([garbage_port, ours_port])
    started = []

    class Process:
        def __init__(self, port):
            self.port, self.kills = port, 0
            started.append(self)

        def kill(self):
            self.kills += 1

    try:
        process, ws_url = edge.start_devtools(
            Process, pick_port=ports.__next__, limit_s=2.0
        )
    finally:
        ours.shutdown()
        ours.server_close()
        garbage.close()
    assert [p.port for p in started] == [garbage_port, ours_port]
    assert started[0].kills >= 1
    assert process is started[1]
    assert ws_url.endswith("/devtools/browser/a")
