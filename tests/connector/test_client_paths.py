"""ADR-002: a URL that climbs out of /sites/WFR-USTEAM/ is refused, also when the dots or slashes are encoded."""

import pytest

from riro.connectors.sharepoint.client import FOLDER_URL, LIST_URL, check_url

SITE = "https://ts.accenture.com/sites/WFR-USTEAM/"


@pytest.mark.parametrize(
    "path",
    [
        "../OTHER/",
        "x/../../OTHER/",
        "%2e%2e/OTHER/",
        "%2E%2E/OTHER/",
        ".%2e/OTHER/",
        "..%2fOTHER/",
        "x%2F..%2F..%2FOTHER/",
        "..%5cOTHER/",
        "..\\OTHER/",
        "x\\..\\..\\OTHER/",
        "%252e%252e/OTHER/",
    ],
)
def test_adr002_check_url_refuses_climbing_out_of_the_site(path):
    with pytest.raises(ValueError):
        check_url(SITE + path)


@pytest.mark.parametrize(
    "url",
    [
        FOLDER_URL,
        LIST_URL,
        SITE + "Shared%20Documents/Synthetic%20file.xlsx",
        SITE + "_api/web/GetFileById('0000-aaaa-1111')/$value",
        SITE + "a..b/file.xlsx",
    ],
)
def test_adr002_check_url_still_accepts_normal_site_urls(url):
    check_url(url)
