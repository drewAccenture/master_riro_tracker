"""Plain words for the sync box (US-07). The error's own text is never shown."""

from riro.connectors.sharepoint.client import FOLDER_PATH
from riro.connectors.sharepoint.errors import ConnectorError, EdgeNotStarted
from riro.services.sync_files import FolderResult

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


def summary(folder: FolderResult) -> str:
    read = folder.updated + folder.unchanged
    if not folder.skipped:
        return f"Sync OK: {read} files read ({folder.updated} updated, {folder.unchanged} unchanged)."
    skipped = len(folder.skipped)
    files = "1 file was skipped." if skipped == 1 else f"{skipped} files were skipped."
    return f"Sync partly worked: {read} of {folder.total} files read. {files}"
