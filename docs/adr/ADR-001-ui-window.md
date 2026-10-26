# ADR-001: UI = pywebview desktop window with HTML/CSS/JS

Status: Accepted
Date: 2026-10-26

## Context
US-11 asks for the same look as the original HTML tracker. The PMO has basic computer skills: she should see one app
window, not a browser tab or a server. The first attempt used a localhost web server and a browser tab, which needed
a token and cookie setup and showed old data when the app had stopped (its DECISIONS row 103).

## Decision
Use pywebview (Windows backend: WinForms + WebView2 through pythonnet). Screens are HTML, CSS and JS that take their
look from the original. The page calls Python through one JS function, `api.call(name, args)`, which maps to
`ui/bridge.py`. No port, no server. Closing the window ends the app.

Slice 1 must show that pywebview starts from the embeddable Python on the PMO's laptop. The diagnostic report records
the pywebview version, the renderer it used (must be `edgechromium`) and the WebView2 runtime version.

## Fallback if pywebview does not run on her laptop
Python's built-in `http.server` on `127.0.0.1` with a random port and a random per-start key, and the app opens Edge in
app mode (`msedge --app=http://127.0.0.1:<port>/?k=<key>`), which looks like a window without browser bars. The same
HTML/CSS/JS is used. Only two things change: `api.call` sends a POST instead of a pywebview call, and `bridge.py` is
served as small JSON endpoints. The app ends when the Edge app window closes (watched through its process handle).
Switching needs a new ADR that supersedes this one.

## Alternatives considered
- Localhost server + normal browser tab (first attempt): works, but it is the fallback, not the default, for the
  reasons in Context.
- Tkinter or Qt: cannot reproduce the original look without rebuilding every screen; Qt adds about 100 MB.

## Consequences
- One window, one process, simple for the PMO.
- Adds pythonnet, clr-loader and cffi (compiled) to the package. Risk that .NET loading fails inside the embeddable
  Python: covered by slice 1 and the fallback.
- The UI layer stays thin and swappable because every call goes through `api.call` and `bridge.py`.
