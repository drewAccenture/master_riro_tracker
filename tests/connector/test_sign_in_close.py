"""ADR-010: how each Edge ends around a sign-in. Only a finished sign-in closes the visible Edge politely.

The fake process records every close() and kill() in order, so a polite close that silently became a kill fails.
"""

import pytest
from sharepoint_fakes import LOGIN_URL, FakeClock, FakePage

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import (
    FOLDER_URL,
    EdgeSession,
    Limits,
    SharePointClient,
)
from riro.connectors.sharepoint.session import GRACEFUL_CLOSE_S

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=1.0, sign_in_s=2.0
)


class OrderedProcess:
    """Records ("close", timeout_s) and ("kill",) in the order they happen."""

    def __init__(self):
        self.calls = []

    def close(self, timeout_s):
        self.calls.append(("close", timeout_s))

    def kill(self):
        self.calls.append(("kill",))


class Edges:
    """start_edge(headless, url) that hands out the given pages in order, each with an OrderedProcess."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.started = []  # (headless, process)

    def __call__(self, headless, url):
        process = OrderedProcess()
        self.started.append((headless, process))
        return EdgeSession(process=process, page=self.pages.pop(0))

    def process(self, n):
        return self.started[n][1]


def make_client(edges):
    clock = FakeClock()
    return SharePointClient(edges, limits=SMALL, clock=clock, sleep=clock.sleep)


# --- M1: the headless Edge running before a sign-in is killed at once ------------------------------------------


def test_adr010_headless_edge_before_sign_in_is_killed_without_polite_close():
    edges = Edges(FakePage(), FakePage(urls=[FOLDER_URL]), FakePage())
    client = make_client(edges)
    client.health_ping()  # a headless Edge is running
    client.sign_in()
    assert edges.started[0][0] is True
    assert edges.process(0).calls == [("kill",)]


# --- M2: the visible Edge after a sign-in ------------------------------------------------------------------------


def test_adr010_finished_sign_in_closes_visible_edge_politely_then_kills():
    edges = Edges(FakePage(urls=[FOLDER_URL]), FakePage())
    client = make_client(edges)
    client.sign_in()
    assert edges.started[0][0] is False
    assert edges.process(0).calls == [("close", GRACEFUL_CLOSE_S), ("kill",)]


def test_adr010_sign_in_not_finished_in_time_kills_visible_edge_at_once():
    edges = Edges(FakePage(urls=[LOGIN_URL]))
    client = make_client(edges)
    with pytest.raises(errors.TimedOut):
        client.sign_in()
    assert edges.process(0).calls == [("kill",)]


def test_adr010_sign_in_window_closed_kills_visible_edge_at_once():
    edges = Edges(FakePage(urls=[LOGIN_URL, errors.Unreachable()]))
    client = make_client(edges)
    with pytest.raises(errors.Unreachable):
        client.sign_in()
    assert edges.process(0).calls == [("kill",)]


def test_adr010_app_exit_during_sign_in_kills_visible_edge_without_polite_close():
    holder = {}

    class ClosingPage(FakePage):
        def current_url(self, *, timeout_s):
            holder["client"].shutdown()
            return LOGIN_URL

    edges = Edges(ClosingPage())
    client = make_client(edges)
    holder["client"] = client
    with pytest.raises(errors.ConnectorError):
        client.sign_in()
    calls = edges.process(0).calls
    assert ("kill",) in calls
    assert not any(call[0] == "close" for call in calls)
