# ADR-008: Checks = a local script instead of Claude Code hooks

Status: Accepted. Refined by ADR-011.
Date: 2026-10-27

## Context
The plan was a PostToolUse hook (ruff format after Write/Edit) and a Stop hook (unit tests). The org's
server-managed Claude Code policy sets `allowManagedHooksOnly: true`, which blocks user, project and local hooks.
Two scratch tests (Write, then Edit) confirmed the project hooks never ran. We cannot change that policy.

## Decision
- `tools\check.ps1` runs, in order: `ruff format src tests`, `ruff check src tests`, `pytest tests\unit -q`.
- It uses `.venv\Scripts\python.exe` by path. Pytest exit 0 or 5 is a pass. Any other failure prints the output
  and exits non-zero. No network calls, no git commands.
- Each step has a timeout (60 s ruff, 120 s pytest).
- CLAUDE.md requires Claude to run it and paste the output before saying "done".
- The hooks block and `.claude\hooks\` are removed. Deny rules in `.claude\settings.json` stay.

## Alternatives considered
- Keep the hooks and wait for a policy exception: no date, and the checks would silently not run. Rejected.
- A git pre-commit hook: does not run before Claude says "done", and commits happen rarely. Possible later.
- Asking the admin to add our hooks to managed settings: org-wide change for one project. Not pursued for now.

## Consequences
Checks are no longer guaranteed. They rely on Claude following CLAUDE.md and on review of the pasted output.
If the policy changes, a new ADR can bring the hooks back.
