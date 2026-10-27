"""ADR-002, ADR-009: starting Edge never opens, lists or checks the profile folder or anything inside it.

The profile path only goes on Edge's command line. A DevToolsActivePort file sits in the fake profile as a trap: if
our code read it, it would find the trap server's port.
"""

import builtins
import io
import os
from pathlib import Path

from sharepoint_fakes import FakeLauncher, edge_answer, json_body, ports

from riro.connectors.sharepoint import edge

LIMIT_S = 1.5


def test_adr009_profile_folder_is_never_opened_listed_or_checked(
    servers, tmp_path, monkeypatch
):
    trap = servers(lambda port: json_body(edge_answer(port)))
    ours = servers(lambda port: json_body(edge_answer(port)))
    profile = tmp_path / "edge_profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(
        f"{trap.port}\n/devtools/browser/trap\n", encoding="utf-8"
    )
    exe = tmp_path / "msedge.exe"
    commands, touched = [], []
    root = os.path.normcase(os.path.abspath(profile))

    def at_or_under_profile(path) -> bool:
        # String compare only: Path.resolve() would call os.stat itself and loop back into the watch.
        try:
            full = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        except (TypeError, ValueError):
            return False
        return full == root or full.startswith(root + os.sep)

    def watch(module, name):
        real = getattr(module, name)

        def wrapper(path=".", *args, **kwargs):
            if not isinstance(path, int) and at_or_under_profile(path):
                touched.append((f"{module.__name__}.{name}", os.fsdecode(path)))
            return real(path, *args, **kwargs)

        monkeypatch.setattr(module, name, wrapper)

    for module, name in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "listdir"),
        (os, "scandir"),
        (os, "stat"),
        (os, "lstat"),
        (os.path, "isdir"),
        (os.path, "exists"),
    ]:
        watch(module, name)
    real_exists = Path.exists

    def exists(self, *args, **kwargs):
        if at_or_under_profile(self):
            touched.append(("Path.exists", str(self)))
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists)

    def on_launch(port):
        commands.append(
            edge.build_command(exe, profile, port, headless=True, url="about:blank")
        )

    launch = FakeLauncher(on_launch)
    _, ws_url = edge.start_devtools(launch, pick_port=ports(ours.port), limit_s=LIMIT_S)

    assert touched == []
    assert trap.paths == []
    assert ws_url.startswith(f"ws://127.0.0.1:{ours.port}/")
    assert f"--user-data-dir={profile}" in commands[0]
    assert f"--remote-debugging-port={ours.port}" in commands[0]
    assert "--remote-debugging-port=0" not in commands[0]
