# ADR-012: pywebview serves ui/web from a local server on 127.0.0.1 (refines ADR-001)

Status: Accepted
Date: 2026-10-27

## Context
ADR-001 says "No port, no server". pywebview 6.2.1 starts its own HTTP server (bottle) whenever a window URL is a
local file, even with `http_server=False` (`webview/__init__.py`, lines 272 to 278). The app opens
`ui/web/index.html` as a local path, so the server always runs.

Checked on 2026-10-27, from pywebview's source and with one run of the app's window on the maintainer's PC (throwaway
data folders, no Connect, no Edge, no SharePoint):
- Address `http://127.0.0.1:<port>/`. bottle binds to 127.0.0.1 only. The port is random (1023 to 65535) because
  `private_mode` is on; in the run it was 2890. The window loads `http://127.0.0.1:<port>/index.html`.
- It serves the files of `ui/web` (`GET /index.html` gave the page; `GET /` gave a 500 error from pywebview's own
  route, harmless).
- It also answers `POST /js_api/<server id>`, with `Access-Control-Allow-Origin: *`. With a foreign `Origin` header
  the POST got 200 and an empty body, and it did not reach the bridge: 0 bridge calls, and pywebview logged
  "JS callback function is not set". On the WebView2 backend the page calls Python through WebView2 messaging, not
  through this endpoint. A wrong id gives 405. No secret token is involved: the server id is a time-based uuid1.
- The server ends with the app process.

## Decision
- Accept the server as pywebview runs it: 127.0.0.1 only, random port, `private_mode` on, serving `ui/web` only,
  ending with the app. No fixed port and no `http_server=True`.
- The bridge stays reachable only through WebView2 messaging, as today. The page calls the four bridge methods
  directly as `window.pywebview.api.<method>()`; ADR-001's one `api.call(name, args)` function was not built.
- `ui/web` holds only the page's HTML, CSS and JS: never data, logs or anything personal.

## Alternatives considered
- Load the page as a `file://` URL so no server starts: not proven that the bridge works for a `file://` page.
  Possible later, with its own check.
- Serve the page ourselves: more code for the same result. Rejected.

## Consequences
- US-15 still holds: the app can be reached only from her laptop.
- Any program of the same Windows user can read the page's HTML, CSS and JS while the app runs. They hold no data.
- After a pywebview upgrade, re-check that `POST /js_api` still does not reach the bridge (it answers any origin).
