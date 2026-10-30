"""Composition root: data folder, diagnostics, connector, services, window. Wiring only, nothing runs at import."""

import os
import platform
import re
from importlib import metadata
from pathlib import Path

import webview

from riro.connectors.sharepoint.client import Limits, SharePointClient
from riro.connectors.sharepoint.edge import make_start_edge
from riro.connectors.sharepoint.errors import Unreachable
from riro.services.autosync import AutoSync
from riro.services.diagnostics import Diagnostics
from riro.services.joiners import JoinerService
from riro.services.report_sections import (
    DATA_TITLE,
    SYNCS_TITLE,
    data_lines,
    sync_run_lines,
)
from riro.services.screens import Screens
from riro.services.sync import SyncService
from riro.store.datafile import DataFile
from riro.store.repo import Repo, check_layout
from riro.ui.bridge import Bridge

APP_VERSION = "0.1.0"
WEB = Path(__file__).resolve().parent / "ui" / "web" / "index.html"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def demo_mode(environ) -> bool:
    """Dev only: RIRO_DATA_DIR set to an absolute folder (the slice 5 visual check on synthetic data)."""
    override = str(environ.get("RIRO_DATA_DIR", "")).strip()
    return bool(override) and Path(override).is_absolute()


def app_root(environ) -> Path:
    """The app folder: LOCALAPPDATA/RIROTracker, or the RIRO_DATA_DIR folder in demo mode."""
    if demo_mode(environ):
        return Path(str(environ["RIRO_DATA_DIR"]).strip())
    return Path(environ["LOCALAPPDATA"]) / "RIROTracker"


class OfflineConnector:
    """Demo mode never reaches SharePoint, so real joiner data never lands in a demo folder."""

    def _refuse(self, *args):
        raise Unreachable("demo mode: SharePoint is switched off")

    sign_in = health_ping = list_files = download = _refuse

    def close(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def signed_in_before(profile: Path) -> bool:
    """True once Connect has run on this PC: Edge made its profile folder.

    Only the folder itself is checked. Nothing inside it is opened, listed or checked (ADR-002).
    """
    return profile.is_dir()


def main() -> None:
    root = app_root(os.environ)
    diagnostics = Diagnostics(
        root / "logs",
        versions={
            "app": APP_VERSION,
            "python": platform.python_version(),
            "pywebview": _package_version("pywebview"),
        },
    )
    profile = root / "edge_profile"  # passed to Edge only, never opened by our code
    limits = Limits()
    start_edge = make_start_edge(
        profile,
        limit_s=limits.edge_start_s,
        on_event=diagnostics.event,
        on_version=lambda product: diagnostics.set_version("edge", product),
    )
    connector = SharePointClient(start_edge, limits=limits, on_event=diagnostics.event)
    if demo_mode(os.environ):
        connector = OfflineConnector()
        diagnostics.set_version(
            "data folder", "demo (RIRO_DATA_DIR), SharePoint switched off"
        )
    repo = Repo(DataFile(root / "data" / "tracker.json", validate=check_layout))
    diagnostics.add_section(SYNCS_TITLE, lambda: sync_run_lines(repo))
    diagnostics.add_section(DATA_TITLE, lambda: data_lines(repo, repo.load_note))
    service = SyncService(connector, diagnostics, repo=repo)
    autosync = AutoSync(service)
    joiners = JoinerService(repo)
    windows = []  # the window is made after the bridge; the picker only runs once it is open

    def pick_files():
        # US-13: Windows' own file dialog, .xlsx only, one or more files. None when cancelled.
        return windows[0].create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("Checklist files (*.xlsx)",),
        )

    bridge = Bridge(
        service,
        diagnostics,
        autosync,
        data_note=repo.load_note,
        joiners=joiners,
        screens=Screens(joiners),
        pick_files=pick_files,
    )
    window = webview.create_window(
        "Master RIRO Tracker",
        url=str(WEB),
        js_api=bridge,
        width=900,
        height=640,
    )
    windows.append(window)

    def on_loaded() -> None:
        diagnostics.set_version(
            "renderer", str(getattr(webview, "renderer", "unknown"))
        )
        agent = str(window.evaluate_js("navigator.userAgent") or "")
        found = re.search(r"Edg/([\d.]+)", agent)
        diagnostics.set_version("webview2", found.group(1) if found else "unknown")

    def sync_on_start() -> None:
        # "Connected" is decided by this sync (NeedsSignIn = not connected). Before the first Connect there is
        # no profile folder, so there is nothing to try. Only the folder's existence is checked, nothing inside.
        # US-06: then every 5 minutes, unless the sign-in expired (US-08: Connect starts it again).
        if signed_in_before(profile) and service.sync().state != "not_connected":
            autosync.start()

    window.events.loaded += on_loaded
    webview.start(
        sync_on_start
    )  # pywebview runs it on its own thread; returns once the window is closed
    finish(service, diagnostics, autosync)


def finish(service, diagnostics, autosync=None) -> None:
    """App exit: stop auto-sync, close Edge (up to 5 s, ADR-010), then the log, so the exit event reaches logs\\."""
    if autosync is not None:
        autosync.stop()
    service.shutdown()
    diagnostics.close()


if __name__ == "__main__":
    main()
