# ADR-010: Close Edge politely for at most 5 s, then kill it by its handle (refines ADR-002)

Status: Accepted
Date: 2026-10-27

## Context
ADR-002 ends Edge by killing its Job Object, with no graceful close to wait for. Measured on 2026-10-27 on the
maintainer's PC (Edge 156.0.4314.42), with throwaway profiles and a local test page: a cookie set just before Edge
ends is lost every time Edge is killed (6 of 6, headless and visible), and kept every time Edge is first asked to
close (6 of 6, 2.0 to 5.0 s). Edge keeps new cookies in memory for a while before saving them to its profile.

What breaks if Edge is always killed:
- Day 1: the visible window is killed right after she signs in. The new sign-in is not saved yet, so the headless
  Edge started next has none, and the first sync says "Your SharePoint sign-in has expired" a moment after she
  signed in.
- Day 2: sign-ins Edge renewed during the day are lost when the app closes, so she has to sign in visibly more often
  (US-08 target: about once per working day).
The measurement used a local test cookie, not Microsoft's. The Day 1 and Day 2 reports confirm it for SharePoint.

## Decision
- A polite close happens in two cases only: after a sign-in that finished, and at app exit.
- Polite close = DevTools `Browser.close`, then wait for Edge to exit. Both share one limit of 5 s
  (`GRACEFUL_CLOSE_S` in `connectors/sharepoint/session.py`).
- After that the job is always killed by its handle, also when Edge already exited or ignored the close.
- Every other end stays as ADR-002 says, a kill at once: time-outs, a lost connection, the whole-sync watchdog, a
  sign-in that did not finish, and the app closed during sign-in.
- The 5 s is a hard limit. Nothing waits on a lock.

## Alternatives considered
- Kill only (ADR-002 as written): loses a fresh sign-in (measured above). Rejected.
- A longer or unlimited polite close: brings back the first attempt's hang (ADR-002 context). Rejected.
- Asking Edge through DevTools to save cookies: needs the cookie commands, and our code never touches cookies.
  Rejected.

## Consequences
- App exit and the switch from visible to headless Edge take up to 5 s longer (measured 2 to 5 s).
- If Edge ignores the close, it is killed after 5 s: the same end state as ADR-002.
- Tested in `tests/connector/test_graceful_close.py` with a fake Edge that ignores the close.
