"""ADR-002, US-07, US-08: GET only to ts.accenture.com/sites/WFR-USTEAM/, status mapping, renew once and retry once."""

import pytest
from sharepoint_fakes import (
    LOGIN_URL,
    NETWORK_ERROR,
    REDIRECT,
    FakeClock,
    FakeEdge,
    FakePage,
    ok,
    ok_json,
    status,
)

from riro.connectors.sharepoint import errors
from riro.connectors.sharepoint.client import (
    FOLDER_URL,
    SITE_URL,
    Limits,
    SharePointClient,
    build_fetch_js,
    check_url,
)

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=0.5, sign_in_s=2.0
)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
ITEM = {
    "Name": "Synthetic checklist 1.xlsx",
    "UniqueId": "0000-aaaa-1111",
    "ETag": '"{0000-AAAA-1111},3"',
    "TimeLastModified": "2026-10-20T08:00:00Z",
    "Length": "12345",
}
# Both common SharePoint REST answer shapes (odata=nometadata "value", odata=verbose "d.results").
LISTING = {"value": [ITEM], "d": {"results": [ITEM]}}


def make_client(*pages):
    clock = FakeClock()
    edge = FakeEdge(*pages)
    return SharePointClient(edge, limits=SMALL, clock=clock, sleep=clock.sleep), edge


def assert_get_only_on_site(expression):
    assert '"GET"' in expression
    assert '"manual"' in expression
    assert "ts.accenture.com" in expression
    assert "/sites/WFR-USTEAM/" in expression
    for method in WRITE_METHODS:
        assert method not in expression


# --- ADR-002 check_url -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        SITE_URL,
        FOLDER_URL,
        "https://ts.accenture.com/sites/WFR-USTEAM/_api/web/GetFileById('0000-aaaa-1111')/$value",
    ],
)
def test_adr002_check_url_accepts_the_site(url):
    check_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://ts.accenture.com/sites/WFR-USTEAM/",
        "ftp://ts.accenture.com/sites/WFR-USTEAM/",
        "https://ts.accenture.com.evil.com/sites/WFR-USTEAM/",
        "https://evil.com/sites/WFR-USTEAM/",
        "https://sub.ts.accenture.com/sites/WFR-USTEAM/",
        "https://user@ts.accenture.com/sites/WFR-USTEAM/",
        "https://user:pw@ts.accenture.com/sites/WFR-USTEAM/",
        "https://ts.accenture.com@evil.com/sites/WFR-USTEAM/",
        "https://ts.accenture.com:8443/sites/WFR-USTEAM/",
        "https://ts.accenture.com:443/sites/WFR-USTEAM/",
        "https://ts.accenture.com/sites/WFR-USTEAM-OTHER/",
        "https://ts.accenture.com/sites/WFR-USTEAM",
        "https://ts.accenture.com/sites/OTHER/",
        "https://ts.accenture.com/",
        "",
        "not a url",
    ],
)
def test_adr002_check_url_refuses_anything_else(url):
    with pytest.raises(ValueError):
        check_url(url)


def test_adr002_fetch_js_is_get_with_manual_redirect():
    js = build_fetch_js(SITE_URL + "_api/web/lists")
    assert_get_only_on_site(js)
    assert "fetch" in js


@pytest.mark.parametrize(
    "url",
    ["https://evil.com/sites/WFR-USTEAM/", "http://ts.accenture.com/sites/WFR-USTEAM/"],
)
def test_adr002_fetch_js_refuses_a_bad_url(url):
    with pytest.raises(ValueError):
        build_fetch_js(url)


# --- ADR-002 every request the client sends ---------------------------------------------------------------------


def test_adr002_every_list_and_download_request_is_a_get_on_the_site():
    page = FakePage(fetches=[ok_json(LISTING), status(401), ok(b"PK-bytes")])
    client, _ = make_client(page)
    client.list_files()
    client.download("0000-aaaa-1111")  # 401, renew, retry: two more fetches
    assert len(page.fetch_expressions) == 3
    assert (
        page.expressions == page.fetch_expressions
    )  # nothing but fetch JS is evaluated
    for expression in page.expressions:
        assert_get_only_on_site(expression)


def test_adr002_renewal_navigates_only_to_the_folder_page():
    page = FakePage(fetches=[REDIRECT, ok(b"x")])
    client, _ = make_client(page)
    client.download("0000-aaaa-1111")
    assert page.navigations == [FOLDER_URL]


# --- list and download results --------------------------------------------------------------------------------


def test_us07_list_files_returns_plain_dicts():
    client, _ = make_client(FakePage(fetches=[ok_json(LISTING)]))
    files = client.list_files()
    assert len(files) == 1
    item = files[0]
    assert set(item) == {"id", "name", "etag", "modified", "size"}
    assert item["id"] == "0000-aaaa-1111"
    assert item["name"] == "Synthetic checklist 1.xlsx"
    assert item["etag"] == '"{0000-AAAA-1111},3"'
    assert int(item["size"]) == 12345


def test_us07_download_returns_decoded_bytes():
    client, _ = make_client(FakePage(fetches=[ok(b"PK\x03\x04synthetic")]))
    assert client.download("0000-aaaa-1111") == b"PK\x03\x04synthetic"


# --- status mapping -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (status(403), errors.NoAccess),
        (status(404), errors.NotFound),
        (NETWORK_ERROR, errors.Unreachable),
    ],
    ids=["403", "404", "network-error"],
)
@pytest.mark.parametrize("method", ["list_files", "download"])
def test_us07_status_maps_to_error(method, answer, error):
    page = FakePage(fetches=[answer])
    client, _ = make_client(page)
    call = (
        client.list_files
        if method == "list_files"
        else lambda: client.download("0000-aaaa-1111")
    )
    with pytest.raises(error):
        call()
    assert len(page.fetch_expressions) == 1
    assert page.navigations == []


@pytest.mark.parametrize(
    "expired", [status(401), REDIRECT], ids=["401", "opaqueredirect"]
)
def test_us08_expired_renews_once_then_retries_once_and_succeeds(expired):
    page = FakePage(
        fetches=[expired, ok(b"after-renewal")], urls=[LOGIN_URL, FOLDER_URL]
    )
    client, edge = make_client(page)
    assert client.download("0000-aaaa-1111") == b"after-renewal"
    assert page.navigations == [FOLDER_URL]
    assert len(page.fetch_expressions) == 2
    assert len(edge.calls) == 1


@pytest.mark.parametrize(
    "expired", [status(401), REDIRECT], ids=["401", "opaqueredirect"]
)
@pytest.mark.parametrize("method", ["list_files", "download"])
def test_us08_still_expired_after_renewal_raises_needs_sign_in(method, expired):
    page = FakePage(fetches=[expired, expired], urls=[FOLDER_URL])
    client, _ = make_client(page)
    call = (
        client.list_files
        if method == "list_files"
        else lambda: client.download("0000-aaaa-1111")
    )
    with pytest.raises(errors.NeedsSignIn):
        call()
    assert page.navigations == [FOLDER_URL]
    assert len(page.fetch_expressions) == 2


def test_us08_renewal_not_back_on_site_in_time_raises_needs_sign_in_without_retry():
    page = FakePage(fetches=[status(401)], urls=[LOGIN_URL])
    client, _ = make_client(page)
    with pytest.raises(errors.NeedsSignIn):
        client.list_files()
    assert len(page.fetch_expressions) == 1
