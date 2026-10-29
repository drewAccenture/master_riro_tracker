"""ADR-003: a DevTools call waiting for another call to finish waits no longer than its own limit."""

import threading
import time

import pytest

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.cdp import CdpClient


class SlowTransport:
    """recv waits its full timeout and never answers."""

    def __init__(self):
        self.entered = threading.Event()

    def send(self, text):
        self.entered.set()

    def recv(self, timeout_s):
        time.sleep(timeout_s)
        raise TimeoutError

    def close(self):
        pass


def test_adr003_second_call_gives_up_within_its_own_limit():
    transport = SlowTransport()
    client = CdpClient(transport)
    first = threading.Thread(
        target=lambda: pytest.raises(
            errors.TimedOut, client.call, "A.a", timeout_s=2.0
        ),
        daemon=True,
    )
    first.start()
    assert transport.entered.wait(timeout=5)
    start = time.monotonic()
    with pytest.raises(errors.TimedOut):
        client.call("Browser.close", timeout_s=0.2)
    assert time.monotonic() - start < 1.0
    first.join(timeout=5)
