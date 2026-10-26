# Constraints

Date: 2026-10-26. Versions checked on PyPI and python.org on this date, not from memory.

## Platform

- Windows 11, the PMO's Accenture laptop, no admin rights.
- Microsoft Edge installed (used for SharePoint sign-in and reading).
- WebView2 runtime and .NET Framework 4.8.x ship with Windows 11 (needed by pywebview). Checked on her laptop in slice 1.

## Python

| Item | Version | Source |
|---|---|---|
| Python, packaged runtime | **3.13.17**, `python-3.13.17-embed-amd64.zip` | python.org/ftp, file present, dated 2026-10-21 (latest 3.13.x) |
| Python, dev venv | 3.13.x, same minor as the runtime | A test fails if `sys.version_info` minor differs |

Why 3.13 and not 3.14 (installed on the dev PC): `openpyxl` has no classifier past 3.11 and `pywebview` none past 3.13.
3.13 keeps every package inside its stated range or one step from it.

Embeddable Python notes: it has no pip. Packages are installed at build time with
`pip install --target <runtime>\Lib\site-packages --python-version 3.13 --only-binary=:all: --platform win_amd64`
(sdist-only packages are built to wheels on the dev PC first), and `python313._pth` lists that folder.

## Approved runtime packages

Checked on PyPI 2026-10-26. "3.13 support" means: wheel and `requires_python` allow 3.13, and the classifier lists 3.13
unless said otherwise.

| Package | Pin | Why | 3.13 support | Wheel |
|---|---|---|---|---|
| pywebview | 6.2.1 | Desktop window with HTML (ADR-001) | yes (classifiers 3.10 to 3.13) | `py3-none-any` |
| pythonnet | 3.2.1 | pywebview's Windows backend (WinForms + WebView2) | yes (`>=3.11,<3.16`) | `cp311.cp312.cp313.cp314.cp315-none-any` |
| clr-loader | 0.3.1 | Needed by pythonnet | `>=3.10`, no classifier | `py3-none-any` |
| cffi | 2.1.1 | Needed by clr-loader, compiled | yes | `cp313-cp313-win_amd64` present |
| pycparser | 3.12 | Needed by cffi | yes | `py3-none-any` |
| bottle | 0.13.4 | Needed by pywebview | yes | `py2.py3-none-any` |
| proxy-tools | 0.1.0 | Needed by pywebview | no metadata (2014) | **sdist only**, built to a wheel at build time |
| typing-extensions | 4.16.0 | Needed by pywebview | yes | `py3-none-any` |
| openpyxl | 3.1.5 | Read `.xlsx` (read-only mode) | `>=3.8`; classifiers stop at 3.11. Pure Python | `py2.py3-none-any` |
| et-xmlfile | 2.0.0 | Needed by openpyxl | yes | `py3-none-any` |
| websocket-client | 1.9.2 | Talk to Edge's DevTools endpoint (ADR-002) | yes | `py3-none-any` |

**Unverified until slice 1:** pythonnet loading .NET from inside the embeddable Python, on the PMO's laptop. PyPI
metadata says it is supported; only a real run proves it. openpyxl on 3.13 is proven by the test suite running on 3.13.

Exact versions of every package (including sub-dependencies) go in a lock file. No new runtime package without an ADR.

## Dev-only packages

| Package | Pin |
|---|---|
| pytest | 9.1.1 |

Others (a linter) are chosen in Phase 4.

## Not allowed

- Playwright, Selenium, Node.js, browser downloads (ADR-002).
- Microsoft Graph, Azure/Entra app registration, Power Automate, OneDrive synced folder (requirements, out of scope).
- Any SharePoint request other than GET.
- Reading, copying or logging cookies, tokens or the Edge profile files.
- Real checklist files in git.
- A database server or ORM (ADR-004).

## Limits

| What | Limit | Where from |
|---|---|---|
| Files in the folder | about 50, read up to 200 | Assumption 4 |
| File size | under 10 MB, larger skipped with a message | Assumption 4 |
| Auto-sync interval | 5 minutes, not a setting | Assumption 5 |
| Time limits | see ADR-003 | |
| Folder depth | one level | Requirements section 3 |
| Allowed host and site | `ts.accenture.com`, `/sites/WFR-USTEAM/` | Requirements section 3 |

## Data location

`%LOCALAPPDATA%\RIROTracker\` (see `docs/architecture.md` section 8). Data on her own laptop, in her user folder
(Assumption 8).
