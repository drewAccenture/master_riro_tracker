# Phases 7 to 10: Integrate, harden, ship, maintain

Contents: Phase 7 Integrations | Phase 8 Hardening | Phase 9 Go-live | Phase 10 Maintain

## Phase 7: Integrations (APIs, connectors, MCP)

- Goal: connect to real systems safely and swappably.
- Artifact: `docs/adr/ADR-0xx-<system>.md`, connector code, contract tests.
- Gate: app works with the connector mocked, and the connector has passed at least one test against a non-production system.

Principles:
- Every external system lives in `src/connectors/<system>/`. Nothing else talks to it.
- Define the contract first (inputs, outputs, errors), then implement.
- Prefer the official SDK. Fall back to raw HTTP only if no maintained SDK exists.
- Handle timeouts, retries, rate limits, auth expiry, bad data.
- Real integration is slower than mocks. Access, permissions, and limits are the usual blockers. Request access early.

```text
Plan the connector for [system, e.g. UKG / Workday / SharePoint].

1. Check if an official SDK exists and is maintained. Recommend SDK vs HTTP.
2. Define the connector contract: methods, inputs, outputs, error types.
   Separate retryable errors from permanent ones.
3. Plan retries, timeouts, rate limiting, pagination, and auth refresh.
   For write operations, say how duplicates are prevented (idempotency).
4. Plan a mock version for tests.
5. Plan contract tests, plus at least one test that runs against a
   non-production instance of the real system.
6. Secrets come only from environment variables. Never hard-code.
7. List the access, permissions, and credentials I must request now,
   and from whom. Use read-only access first where possible.

Draft an ADR for this integration. Do not implement yet.
```

MCP for Claude itself (dev tools):
- Enable only what the current task needs. Too many tools means a distracted Claude and a bigger context.
- Typical useful set: GitHub, Playwright (browser testing), docs lookup, the database (read-only in dev).
- Pin MCP server versions. Review what data goes to external servers.

## Phase 8: Hardening

- Goal: make it safe and reliable before anyone real uses it.
- Artifact: security checklist, test coverage report, e2e tests.
- Gate: checklist all green.
- Role to adopt for the security audit: security reviewer. Report only, never edit.

Checklist (the user ticks these, show it as a list):
- No secrets in code or git history (`.env.example` only)
- Input validation on every entry point
- Auth + role checks on every protected action
- Authorization tested: user A cannot reach user B's data
- Rate limiting on public endpoints
- Errors logged, not shown raw to users
- Audit log for important actions
- Dependencies scanned for known vulnerabilities
- Unit + integration tests pass in CI
- Playwright e2e covers the main user journeys
- Tested with bad data, empty data, huge data

Security audit:

```text
Audit this codebase for:
injection, broken auth, missing authorization checks (can user A reach
user B's data?), exposed secrets (check git history too), missing validation,
insecure dependencies, unsafe file handling, and logging of sensitive data.

For each finding give: severity, file and line, why it matters in plain
English, and the fix.
Propose the fixes as a plan, ordered by severity. Do not edit files.
```

End-to-end tests:

```text
Using Playwright, write e2e tests for these journeys from requirements.md:
[list journeys]. Include one unhappy path per journey.

Rules:
- Each test must be independent. Use stable selectors, not sleeps.
- Do not change application code to make a test pass. Report the bug instead.

Run them and report results with screenshots of failures.
```

AI-generated code often has hidden security gaps. Assume it does until proven otherwise.

## Phase 9: Go-live

- Goal: ship safely with a way back.
- Artifact: `docs/runbook.md`, CI/CD pipeline, release tag.
- Gate: rollback has been tested at least once.

Before go-live:
- CI runs lint + tests + build on every PR.
- Separate environments: dev, test/staging, production.
- Production secrets in a secret store, not in files.
- Monitoring + error tracking on. The user knows where logs go.
- Backup and restore tested.
- Approval from whoever owns the system.

```text
Create docs/runbook.md covering:
1. How to deploy (step by step)
2. How to roll back, including database or data changes
3. Environment variables needed (names only, no values)
4. Health checks to confirm the release works
5. Common incidents and first response
6. Who to contact

Never invent contacts, URLs, or credentials. Mark anything you cannot
know as TODO for me to fill in.

Then propose a CI pipeline (GitHub Actions or our approved tool)
that runs lint, typecheck, tests, and build on every PR.
Pin action versions, use least-privilege tokens, and read secrets only
from the CI secret store.
Show it before saving.
```

Go-live day:
1. Tag the release and update `CHANGELOG.md`.
2. Deploy to staging, smoke test, deploy to production.
3. Watch errors and logs for the first hours.
4. Keep the rollback ready.

## Phase 10: Maintain and evolve

- Goal: keep the codebase healthy as it grows.
- Artifact: updated docs, ADRs, `CHANGELOG.md`, postmortems.

Weekly: run the drift check (Phase 6), update dependencies in a separate branch and run all tests, prune CLAUDE.md.

Per bug:

```text
Bug: [paste error + steps to reproduce].

1. Reproduce it with a failing test first. If you cannot reproduce it,
   stop and tell me what you tried.
2. Find the ROOT CAUSE. Explain it before fixing.
   If the fix touches more than 2 files, stop here and wait for my approval.
3. Fix the cause, not the symptom. No band-aid patches.
   Never weaken or delete an existing test.
4. Check if the same bug pattern exists elsewhere.
5. Run the full test suite and show the output.
```

Per incident:

```text
Draft a blameless postmortem and save it to
docs/postmortems/YYYY-MM-DD-<title>.md with:
timeline, root cause, impact, what fixed it, and actions to prevent it.
Use facts from logs and git only. Mark anything unknown as UNKNOWN.
If Claude caused it or could have prevented it, propose a Gotcha line for
CLAUDE.md. Do not edit CLAUDE.md until I approve.
```

Per refactor: new ADR first, then plan in Plan Mode, then small steps with tests after each. Never refactor and add features in the same branch.

Onboarding a new dev or a new Claude session:

```text
Give me an overview of this codebase using CLAUDE.md and docs/.
Then trace [one feature] from UI to storage.
Do not edit any files.
```
