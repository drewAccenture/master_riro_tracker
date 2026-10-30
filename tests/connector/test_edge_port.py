"""DevTools port chosen by the app and found through /json/version (ADR-009, ADR-003 Edge start limit).

The fakes and the `servers` / `hanging_port` fixtures are in sharepoint_fakes.py. The profile-folder test is in
test_edge_profile.py.
"""

import socket
import time

import pytest
from sharepoint_fakes import FakeLauncher, edge_answer, json_body, ports

from riro.connectors.sharepoint import edge
from riro.connectors.sharepoint.errors import TimedOut

LIMIT_S = 1.5  # small injected limit shared by all attempts
SLACK_S = 1.0


def test_adr003_limits_are_the_decided_values():
    assert edge.DEVTOOLS_START_LIMIT_S == 30.0
    assert edge.DEVTOOLS_ATTEMPTS == 3


def test_adr009_valid_answer_returns_websocket_address(servers):
    server = servers(lambda port: json_body(edge_answer(port)))
    launch = FakeLauncher()

    process, ws_url = edge.start_devtools(
        launch, pick_port=ports(server.port), limit_s=LIMIT_S
    )

    assert ws_url == f"ws://127.0.0.1:{server.port}/devtools/browser/abc"
    assert [p.port for p in launch.started] == [server.port]
    assert process is launch.started[0]
    assert process.kills == 0
    assert server.paths == ["/json/version"]


def test_adr009_never_answers_three_attempts_killed_then_timed_out(hanging_port):
    launch = FakeLauncher()
    start = time.monotonic()

    with pytest.raises(TimedOut, match="Edge could not be started"):
        edge.start_devtools(
            launch,
            pick_port=ports(hanging_port, hanging_port, hanging_port),
            limit_s=LIMIT_S,
        )

    elapsed = time.monotonic() - start
    assert len(launch.started) == 3
    assert all(p.kills >= 1 for p in launch.started)
    assert elapsed < LIMIT_S + SLACK_S


def test_adr009_nothing_listening_three_attempts_killed_then_timed_out():
    launch = FakeLauncher()
    free = [edge.pick_free_port() for _ in range(3)]
    start = time.monotonic()

    with pytest.raises(TimedOut, match="Edge could not be started"):
        edge.start_devtools(launch, pick_port=ports(*free), limit_s=LIMIT_S)

    assert [p.port for p in launch.started] == free
    assert all(p.kills >= 1 for p in launch.started)
    assert time.monotonic() - start < LIMIT_S + SLACK_S


@pytest.mark.parametrize(
    "wrong_answer",
    [
        pytest.param(
            lambda port: json_body(
                {**edge_answer(port), "Browser": "Chrome/130.0.0.0"}
            ),
            id="not_edge",
        ),
        pytest.param(
            lambda port: json_body(
                {
                    **edge_answer(port),
                    "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/x",
                }
            ),
            id="other_port",
        ),
        pytest.param(
            lambda port: json_body(
                {
                    **edge_answer(port),
                    "webSocketDebuggerUrl": f"ws://10.0.0.5:{port}/devtools/browser/abc",
                }
            ),
            id="other_host",
        ),
        pytest.param(lambda port: (200, b"<html>not json</html>"), id="not_json"),
        pytest.param(
            lambda port: json_body({"Browser": "Edg/130.0.2849.68"}), id="no_websocket"
        ),
    ],
)
def test_adr009_answer_not_ours_picks_new_port(servers, wrong_answer):
    foreign = servers(wrong_answer)
    ours = servers(lambda port: json_body(edge_answer(port)))
    launch = FakeLauncher()

    process, ws_url = edge.start_devtools(
        launch, pick_port=ports(foreign.port, ours.port), limit_s=LIMIT_S
    )

    assert [p.port for p in launch.started] == [foreign.port, ours.port]
    assert launch.started[0].kills >= 1
    assert process is launch.started[1]
    assert ws_url == f"ws://127.0.0.1:{ours.port}/devtools/browser/abc"


def test_adr009_port_taken_first_free_second_succeeds_on_attempt_two(servers):
    taken = servers(
        lambda port: (404, b"Not Found")
    )  # another program holds the first port
    ours = servers(lambda port: json_body(edge_answer(port)))
    launch = FakeLauncher()

    process, ws_url = edge.start_devtools(
        launch, pick_port=ports(taken.port, ours.port), limit_s=LIMIT_S
    )

    assert [p.port for p in launch.started] == [taken.port, ours.port]
    assert launch.started[0].port != launch.started[1].port
    assert launch.started[0].kills >= 1
    assert process.kills == 0
    assert ws_url.startswith(f"ws://127.0.0.1:{ours.port}/")


def test_adr009_build_command_headless_and_visible(tmp_path):
    exe, profile = tmp_path / "msedge.exe", tmp_path / "edge_profile"

    headless = edge.build_command(
        exe, profile, 9333, headless=True, url="https://example.test/"
    )
    visible = edge.build_command(
        exe, profile, 9333, headless=False, url="https://example.test/"
    )

    assert headless[0] == str(exe)
    assert "--headless=new" in headless
    assert not any(arg.startswith("--headless") for arg in visible)
    assert headless[-1] == visible[-1] == "https://example.test/"


def test_adr009_pick_free_port_is_bindable_on_localhost():
    port = edge.pick_free_port()
    assert 1024 <= port <= 65535
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
