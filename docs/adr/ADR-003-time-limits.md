# ADR-003: Time limits for sign-in and sync

Status: Accepted
Date: 2026-10-26

## Context
US-07 says a sync never hangs forever and a timed-out sync leaves the next one clean. US-08 asks Phase 2 to set the
silent renewal limit. The first attempt saw silent renewal take about 10 s and a SharePoint request take under 1 s.

## Decision

| Step | Limit | On time-out |
|---|---|---|
| Edge start until DevTools answers | 30 s | Kill job, "Edge could not be started" |
| Health ping before each sync | 5 s | Kill job, start Edge again once |
| One SharePoint request (list or download) | 30 s | Kill job, `TimedOut` |
| Silent renewal | 45 s | "Sign in again", auto-sync stops |
| Visible sign-in | 3 min (US-01) | "The sign-in did not finish" |
| Whole sync | 3 min | Kill job, `TimedOut`, next sync starts clean |

Every limit is a constant in the connector or sync service, with a test that uses a fake Edge that never answers.

## Alternatives considered
Retries with back-off: more code and longer waits; the 5-minute timer already retries. Not now.

## Consequences
A slow network can turn into a reported failure instead of a long wait. The numbers are tuned from slice 1 reports if
needed, with a new ADR.
