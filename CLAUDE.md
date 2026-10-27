# Project
Master RIRO Tracker: a Windows desktop app that reads roll-in checklists from one SharePoint folder (through an
app-owned Edge) and shows joiner progress. Stack: Python 3.13 + pywebview (HTML/CSS/JS) + openpyxl + one JSON data file.

# Read first
- docs/requirements.md   -> what we build (story IDs US-xx)
- docs/architecture.md   -> layers, folder tree, dependency rules
- docs/workflows.md      -> user flow and data flow per story
- docs/constraints.md    -> versions, approved packages, what is not allowed
- docs/glossary.md       -> technical words
- docs/adr/              -> decisions. Do not change a decision without a new ADR.
- docs/plans/            -> current feature plan

# Environment
- Windows 11, PowerShell 5.1 (no `&&` or `||`). One command per call. Use `;` only to join read-only checks.
  Never chain `git commit` or delete commands with anything.
- Always use the project venv: `.venv\Scripts\python.exe`. Never the global Python, never `pip install` outside it.
- Base branch is `developer`, not `main`. Branch from it, diff against it, PR into it.

# Commands
- Check all (format, lint, unit tests): `powershell -File tools\check.ps1`
- Test unit (fast, tools\check.ps1 runs this): `.venv\Scripts\python.exe -m pytest tests\unit -q`
- Test one file: `.venv\Scripts\python.exe -m pytest <file> -q`
- Test all: `.venv\Scripts\python.exe -m pytest -q`
- Format: `.venv\Scripts\python.exe -m ruff format src tests`
- Lint: `.venv\Scripts\python.exe -m ruff check src tests`
- Run app: `.venv\Scripts\python.exe -m riro`
- Build package: `powershell -File tools\build_package.ps1`
- pytest exit code 5 means "no tests collected". That is not a failure.

# Architecture rules (never break)
- ui -> services -> core / store / connectors. Nothing calls upward (docs/architecture.md section 5).
- core is pure: no files, no network, no clock. The date is passed in.
- Status rules live only in src/riro/core/status.py. The page never recomputes them.
- Only src/riro/store/ touches the data file. Only src/riro/connectors/ talks to Edge or SharePoint.
- SharePoint: GET only. Never read, copy or log cookies, tokens or the Edge profile.
- No new package (runtime or dev) without asking me. Runtime packages also need an ADR.
- Files over about 300 lines get split.

# Workflow rules
- Plan before editing more than 2 files.
- Search the repo for existing code before writing new code.
- Every change needs a test. Run tests before saying "done" and paste the output.
- Hooks are blocked by org policy. Before saying done, run tools\check.ps1 and paste the output.
- Never edit a test just to make it pass. If a test is wrong, tell me.
- Tests use synthetic fixtures only (tests/fixtures/). Never real checklist files.
- reference/ is read-only background (old attempt, original HTML). Do not import from it or copy files into git.
- Small commits with clear messages. Do not commit unless I ask.
- If unsure: read docs -> read code -> read tests -> then ask me.

# Gotchas
- The dev venv must be Python 3.13 (same minor as the packaged runtime). Check `.venv\Scripts\python.exe --version`.
- [Add here every time Claude makes the same mistake twice.]
