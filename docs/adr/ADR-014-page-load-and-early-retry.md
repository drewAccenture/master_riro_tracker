# ADR-014: Hidden Edge page load 60 s, one early retry after a failed first sync

Status: Accepted
Date: 2026-11-03

## Context
ADR-003 says its numbers are tuned from real reports with a new ADR. The hidden Edge's first page load (inside an
Edge start, before the health ping) used the 30 s request limit. Real runs: 22 s, more than 30 s four times, about
6 s, 7.9 s on a retry. On 2026-10-30 the 30 s limit made the sync fail. The first sync after the app opens failed
twice on 2026-11-03; the next one worked, but only after the 5-minute timer.

## Decision
- The hidden Edge's first page load may take up to 60 s (was 30 s). Other limits in ADR-003 are unchanged.
- When the sync on app start fails (not "sign-in expired"), the first auto-sync runs after 60 s instead of 5 minutes.
  Later ones stay at 5 minutes. No other retries are added.

## Alternatives considered
- Keep 30 s: the retry inside the sync sometimes saves it, but not always (Day 1).
- 90 s or more: one Edge start would then be 2 minutes of the 3-minute sync limit.
- Retries with back-off (ADR-003 rejected them): still more code than one early tick.

## Consequences
- A truly stuck Edge is found 30 s later. The whole sync limit (3 min) still ends every sync.
- After a failed start she waits about a minute for data, not five.
