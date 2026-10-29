"""US-07, US-01, ADR-003: plain-word messages and the whole-sync limit constant in services/sync.py."""

import pytest

from riro.connectors.sharepoint import errors
from riro.services.sync import SIGN_IN_NOT_FINISHED, SYNC_LIMIT_S, message_for

MESSAGES = {
    "NeedsSignIn": "Your SharePoint sign-in has expired. Click Sign in again.",
    "NoAccess": "You do not have access to the folder. Ask the folder owner for read access.",
    "NotFound": "The folder was not found. It may have been moved or renamed.",
    "Unreachable": "SharePoint could not be reached. Check your network or VPN.",
    "TimedOut": "SharePoint did not answer in time. Click Sync now to try again.",
    "EdgeMissing": "Microsoft Edge was not found. Install Microsoft Edge and try again.",
}


@pytest.mark.parametrize(("kind", "text"), list(MESSAGES.items()))
def test_us07_each_connector_error_maps_to_its_plain_word_message(kind, text):
    assert message_for(getattr(errors, kind)()) == text


@pytest.mark.parametrize("kind", list(MESSAGES))
def test_us07_message_does_not_depend_on_the_error_text(kind):
    error = getattr(errors, kind)(
        "internal detail https://ts.accenture.com/x?token=abc"
    )
    assert message_for(error) == MESSAGES[kind]


def test_us01_sign_in_not_finished_text():
    assert (
        SIGN_IN_NOT_FINISHED
        == "The sign-in did not finish. Click Connect to SharePoint to try again."
    )


def test_adr003_whole_sync_limit_is_three_minutes():
    assert SYNC_LIMIT_S == 180.0
