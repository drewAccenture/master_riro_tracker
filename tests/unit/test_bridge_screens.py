"""US-05, US-11 (plan slice 5, section 3.4): the bridge's overview() and the richer joiner(), plain JSON data.

joiner() keeps every existing key and value; with screens given it gains the joiner page keys.
"""

import json
from datetime import date

import pytest
from screens_fakes import AS_OF, make_service

from riro.services.joiners import BAD_DATE
from riro.services.screens import Screens
from riro.services.sync import SyncResult
from riro.ui.bridge import Bridge


class FakeSync:
    def last_result(self):
        return SyncResult("not_connected", "SharePoint: Not connected")

    def is_running(self):
        return False

    def is_connected(self):
        return False


AS_OF_TEXT = "2026-11-05"
NEW_KEYS = {
    "roll_on_text",
    "as_of_text",
    "hidden",
    "skipped_text",
    "problem_text",
    "roles",
    "banner",
    "meter",
    "tiles",
    "ladder",
    "task_rows",
    "role_note",  # decision B (2026-10-29): counts follow the role filter
}


def make():
    service = make_service()
    screens = Screens(service)
    plain = Bridge(FakeSync(), None, joiners=service)
    rich = Bridge(FakeSync(), None, joiners=service, screens=screens)
    return plain, rich, service, screens


def test_us11_overview_returns_the_screens_overview_for_the_date():
    _, bridge, _, screens = make()
    result = bridge.overview(AS_OF_TEXT)
    assert result == screens.overview(AS_OF)
    assert result["kpis"]["joiners"] == 2
    json.dumps(result)


def test_us11_overview_uses_the_date_the_page_sends():
    _, bridge, _, screens = make()
    assert bridge.overview("2026-11-20") == screens.overview(date(2026, 11, 20))
    assert bridge.overview("2026-11-20") != bridge.overview(AS_OF_TEXT)


@pytest.mark.parametrize("as_of", ["", "05/11/2026", "tomorrow", "2026-13-01"])
def test_us11_overview_with_a_bad_date_gives_the_bad_date_error(as_of):
    _, bridge, _, _ = make()
    assert bridge.overview(as_of) == {"error": BAD_DATE}
    assert bridge.joiner("f-a", as_of) == {"error": BAD_DATE}


@pytest.mark.parametrize("joiner_id", ["f-a", "f-b", "f-w"])
def test_us05_joiner_with_screens_keeps_existing_keys_and_adds_the_page_keys(joiner_id):
    plain, rich, service, screens = make()
    before = plain.joiner(joiner_id, AS_OF_TEXT)
    after = rich.joiner(joiner_id, AS_OF_TEXT)
    assert {k: after[k] for k in before} == before
    assert set(after) == set(before) | NEW_KEYS
    expected = screens.joiner_extra(service.joiner(joiner_id, AS_OF), AS_OF)
    assert {k: after[k] for k in NEW_KEYS} == expected
    json.dumps(after)


def test_us05_bridge_tiles_differ_between_two_joiners():
    _, bridge, _, _ = make()
    alpha = bridge.joiner("f-a", AS_OF_TEXT)
    beta = bridge.joiner("f-b", AS_OF_TEXT)
    assert alpha["tiles"] != beta["tiles"]
    assert alpha["counts"] != beta["counts"]


def test_us03_unknown_joiner_with_screens_is_not_found():
    _, bridge, _, _ = make()
    assert bridge.joiner("no-such-id", AS_OF_TEXT) == {"found": False}


def test_page_sees_only_the_nine_methods_with_screens():
    _, bridge, _, _ = make()
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == {
        "connect",
        "sync_now",
        "last_result",
        "copy_report",
        "joiners",
        "joiner",
        "set_roll_on",
        "overview",
        "import_files",
    }
