"""ADR-003: an Edge start can be stopped from another thread, it has one deadline, and Edge is killed only once.

The `hanging_port` fixture is shared (sharepoint_fakes.py, through conftest.py).
"""

import threading
import time
from pathlib import Path

import pytest

from riro.connectors.sharepoint import edge, errors
from riro.connectors.sharepoint.edge_process import EdgeProcess


class FakeProcess:
    def __init__(self, port=None):
        self.port = port
        self.kills = 0

    def kill(self):
        self.kills += 1


def test_adr003_start_devtools_stops_when_asked(hanging_port):
    started = []
    stop_at = time.monotonic() + 0.2

    def launch(port):
        started.append(FakeProcess(port))
        return started[-1]

    begin = time.monotonic()
    with pytest.raises(errors.TimedOut):
        edge.start_devtools(
            launch,
            pick_port=lambda: hanging_port,
            limit_s=5.0,
            stop=lambda: time.monotonic() > stop_at,
        )
    assert time.monotonic() - begin < 1.5
    assert len(started) == 1  # no new attempt once asked to stop
    assert started[0].kills >= 1


def test_adr003_abort_during_start_kills_edge_and_raises():
    process = FakeProcess()
    holder = {}

    def start(launch_on_port, **kwargs):
        launch_on_port(9333)
        holder["start_edge"].abort()  # the watchdog fires while Edge starts
        return process, "ws://127.0.0.1:9333/devtools/browser/x"

    start_edge = edge.make_start_edge(
        Path("edge_profile"),
        find=lambda: Path("msedge.exe"),
        launch=lambda *a, **k: process,
        start=start,
        connect=lambda ws, t: pytest.fail("must not connect after abort"),
    )
    holder["start_edge"] = start_edge
    with pytest.raises(errors.TimedOut):
        start_edge(True, "https://ts.accenture.com/sites/WFR-USTEAM/")
    assert process.kills >= 1


def test_adr003_start_shares_one_deadline_across_its_steps():
    seen = {}

    def start(launch_on_port, **kwargs):
        seen["limit_s"] = kwargs["limit_s"]
        raise errors.EdgeNotStarted("Edge could not be started")

    start_edge = edge.make_start_edge(
        Path("edge_profile"), find=lambda: Path("msedge.exe"), start=start
    )
    with pytest.raises(errors.EdgeNotStarted):
        start_edge(True, "https://ts.accenture.com/sites/WFR-USTEAM/")
    assert seen["limit_s"] == edge.DEVTOOLS_START_LIMIT_S
    assert edge.START_TOTAL_S == edge.DEVTOOLS_START_LIMIT_S + edge.PAGE_S


# --- Edge is killed once, even when two threads kill it at the same time ------------------------------------------


class SlowKernel32:
    def __init__(self):
        self.closed = []
        self.terminated = []

    def TerminateJobObject(self, job, code):
        self.terminated.append(job)
        time.sleep(0.05)  # widens the window between the check and the close

    def CloseHandle(self, handle):
        self.closed.append(handle)


class FakePopen:
    def kill(self):
        pass


def test_adr002_two_threads_killing_edge_close_the_job_handle_once():
    kernel32 = SlowKernel32()
    process = EdgeProcess(FakePopen(), 1234, kernel32)
    threads = [threading.Thread(target=process.kill) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert kernel32.closed == [1234]
    assert kernel32.terminated == [1234]
