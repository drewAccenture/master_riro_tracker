"""The only SharePoint addresses the app may use, and the GET-only fetch run inside the page (ADR-002)."""

import base64
import json
from urllib.parse import quote, unquote, urlsplit

from riro.connectors.sharepoint.errors import NoAccess, NotFound, Unreachable

SITE_HOST = "ts.accenture.com"
SITE_PATH = "/sites/WFR-USTEAM/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
FOLDER_PATH = (
    "/sites/WFR-USTEAM/Shared Documents/Repo/00 ASSETS/AKN/PMOCC RIRO CHECKLIST"
    "/ROLL-IN CHECKLIST/In Progress Onboarding"
)
FOLDER_URL = (
    f"{SITE_URL}Shared%20Documents/Forms/AllItems.aspx?id={quote(FOLDER_PATH, safe='')}"
)
LIST_URL = (
    f"{SITE_URL}_api/web/GetFolderByServerRelativePath(decodedurl='{quote(FOLDER_PATH)}')"
    "/Files?$select=Name,UniqueId,ETag,TimeLastModified,Length"
)

# The page checks itself first: only a fully loaded site page sends the GET. The reported tab URL can already be the
# site while the document is still a Microsoft login page (checked against real Edge, 2026-10-27).
_FETCH_JS = r"""(async () => {
  const path = location.pathname;
  const ready = location.origin === "https://ts.accenture.com"
    && path.startsWith("/sites/WFR-USTEAM/")
    && !/\/_(layouts|forms|login|trust|windows)\//i.test(path)
    && document.readyState === "complete";
  if (!ready) {
    return {"status": 0, "type": "not_ready", "body_b64": ""};
  }
  try {
    const r = await fetch(%s, {"method": "GET", "redirect": "manual", "credentials": "include",
                              "headers": {"Accept": "application/json;odata=nometadata"}});
    const bytes = new Uint8Array(await r.arrayBuffer());
    let text = "";
    for (let i = 0; i < bytes.length; i += 32768) {
      text += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    }
    return {"status": r.status, "type": r.type, "body_b64": btoa(text)};
  } catch (e) {
    return {"status": 0, "type": "error", "body_b64": ""};
  }
})()"""


def _plain_path(path: str) -> str | None:
    """The path decoded until it stops changing, backslashes as slashes. None if it climbs with . or .."""
    for _ in range(4):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    else:
        return None
    path = path.replace("\\", "/")
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    return path


def is_on_site(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    path = _plain_path(parts.path)
    return (
        parts.scheme == "https"
        and parts.netloc == SITE_HOST
        and path is not None
        and path.startswith(SITE_PATH)
    )


_SIGN_IN_FOLDERS = ("_layouts", "_forms", "_login", "_trust", "_windows")


def is_site_page(url: str) -> bool:
    """On the site and not one of SharePoint's own sign-in pages (architecture section 6.2)."""
    if not is_on_site(url):
        return False
    segments = _plain_path(urlsplit(url).path).lower().split("/")
    return not any(segment in _SIGN_IN_FOLDERS for segment in segments)


def check_url(url: str) -> None:
    if not is_on_site(url):
        raise ValueError("refused: only GET requests on the allowed SharePoint site")


def build_fetch_js(url: str) -> str:
    check_url(url)
    return _FETCH_JS % json.dumps(url)


# --- reading the answer of the fetch above ------------------------------------------------------------------------


def is_not_ready(answer: dict) -> bool:
    """The page was not a loaded site page, so nothing was sent."""
    return answer.get("type") == "not_ready"


def is_expired(answer: dict) -> bool:
    status = answer.get("status")
    return (
        answer.get("type") == "opaqueredirect"
        or status == 401
        or (isinstance(status, int) and 300 <= status < 400)
    )


def read_body(answer: dict) -> bytes:
    status = answer.get("status")
    if status == 403:
        raise NoAccess()
    if status == 404:
        raise NotFound()
    if status != 200:
        raise Unreachable(f"HTTP {status}")
    try:
        return base64.b64decode(answer.get("body_b64") or "", validate=True)
    except ValueError as exc:
        raise Unreachable("unreadable answer") from exc
