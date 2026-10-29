"""The sync result and its plain words for the sync box (US-07). The error's own text is never shown."""

from dataclasses import dataclass
from datetime import datetime

from riro.connectors.sharepoint.client import FOLDER_PATH
from riro.connectors.sharepoint.errors import ConnectorError, EdgeNotStarted
from riro.core.models import HeaderReport

SIGN_IN_NOT_FINISHED = (
    "The sign-in did not finish. Click Connect to SharePoint to try again."
)
SYNCING = "Syncing..."
NOT_CONNECTED = "SharePoint: Not connected"
SAVE_FAILED = "Your data could not be saved. Close other programs that may use it and click Sync now."
EDGE_NOT_STARTED = "Microsoft Edge could not be started. Click Sync now to try again."
UNEXPECTED = (
    "Something went wrong. Click Copy diagnostic report and send it to the maintainer."
)
FOLDER_LABEL = " / ".join(FOLDER_PATH.split("/")[3:])

MESSAGES = {
    "NeedsSignIn": "Your SharePoint sign-in has expired. Click Sign in again.",
    "NoAccess": "You do not have access to the folder. Ask the folder owner for read access.",
    "NotFound": "The folder was not found. It may have been moved or renamed.",
    "Unreachable": "SharePoint could not be reached. Check your network or VPN.",
    "TimedOut": "SharePoint did not answer in time. The app will try again in 5 minutes.",
    "EdgeMissing": "Microsoft Edge was not found. Install Microsoft Edge and try again.",
}


def message_for(error: ConnectorError) -> str:
    """Plain words for the error kind. The error's own text is never shown."""
    if isinstance(error, EdgeNotStarted):
        return EDGE_NOT_STARTED
    return MESSAGES.get(type(error).kind, MESSAGES["Unreachable"])


@dataclass(frozen=True)
class SyncResult:
    state: str  # "ok", "failed", "syncing", "not_connected", "sign_in_not_finished"
    message: str
    files_listed: int = 0
    report: HeaderReport | None = None
    last_success: datetime | None = None
    files_read: int = 0
    updated: int = 0  # files
    unchanged: int = 0  # files
    # (file name, reason), shown on her screen only
    skipped: tuple[tuple[str, str], ...] = ()
    joiners: int = 0  # visible joiners after the sync
    joiners_updated: int = 0  # visible joiners whose file was read again in this sync
    warnings: tuple[
        str, ...
    ] = ()  # e.g. two files with the same Checklist Owner (US-02)


def _joiners(count: int) -> str:
    return "1 joiner" if count == 1 else f"{count} joiners"


def summary(joiners: int, joiners_updated: int, skipped: int) -> str:
    """US-07: how many joiners were updated, and how many files were skipped."""
    if not skipped:
        unchanged = joiners - joiners_updated
        return f"Sync OK: {_joiners(joiners)} ({joiners_updated} updated, {unchanged} unchanged)."
    files = "1 file was skipped." if skipped == 1 else f"{skipped} files were skipped."
    return (
        f"Sync partly worked: {_joiners(joiners)} ({joiners_updated} updated). {files}"
    )
