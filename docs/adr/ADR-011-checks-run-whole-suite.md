# ADR-011: tools\check.ps1 runs the whole test suite except live tests (refines ADR-008)

Status: Accepted
Date: 2026-10-27

## Context
ADR-008 made `tools\check.ps1` run `pytest tests\unit` only. By slice 1 the connector tests (DevTools port,
time-outs, GET-only, Edge start and close) are over half the suite and were outside the checks Claude must run before
saying "done". The full suite takes about 20 s, well inside the 120 s pytest step limit.

## Decision
- `tools\check.ps1` runs `pytest tests -q`: every test except those marked `live`.
- `pyproject.toml` registers the `live` marker, turns on `--strict-markers`, and deselects `live` by default
  (`addopts = -m "not live"`).
- A live test needs both `-m live` and `RIRO_LIVE=1`; without the variable it is skipped. It uses a throwaway Edge
  profile under pytest's temp folder, never `%LOCALAPPDATA%\RIROTracker` or the everyday Edge profile, and it is run
  only after the maintainer says yes (CLAUDE.md).
- The checks still make no network calls beyond 127.0.0.1 and run no git commands.

## Alternatives considered
- Keep unit tests only (ADR-008): misses the connector, where the slice 1 risks are. Rejected.
- Exclude live tests with a path filter in check.ps1: easy to forget when a live test lands in another folder. Rejected.

## Consequences
- The checks take about 20 s instead of about 4 s.
- A mistyped marker fails the run instead of silently running a test.
