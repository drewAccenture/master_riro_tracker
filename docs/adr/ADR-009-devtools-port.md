# ADR-009: DevTools port = chosen by the app, found through /json/version (refines ADR-002)

Status: Accepted
Date: 2026-10-27

## Context
ADR-002 starts Edge with `--remote-debugging-port=0`. With port 0, Edge picks a port and writes it to the file
`DevToolsActivePort` inside the profile folder. Our code must never read anything in the Edge profile (CLAUDE.md,
constraints.md), so that file cannot be used. Edge's stderr line "DevTools listening on ..." was also considered, but
it depends on how Edge is started and on its version.

## Decision
- `connectors/sharepoint/edge.py` picks a free port: bind a socket to `127.0.0.1:0`, read the port, close the socket.
- It starts Edge with `--remote-debugging-port=<port>` (plus the ADR-002 flags) inside the Job Object.
- It polls `http://127.0.0.1:<port>/json/version` (GET, standard library `urllib`) until it answers, and takes
  `webSocketDebuggerUrl` from the answer. The answer is ours only if it is JSON, `Browser` starts with `Edg/`, and the
  websocket address is on `127.0.0.1:<port>`. Anything else counts as "port not ours".
- If Edge cannot bind the port (another program took it between our check and Edge's start), the poll gets no
  answer or an answer that is not ours. Then the job is killed and a new port is picked. At most 3 attempts.
- Time limits stay as ADR-003 says: 30 s in total for "Edge start until DevTools answers", shared by all attempts
  (about 10 s each). After 3 failed attempts: kill the job, `TimedOut`, "Edge could not be started".
- Nothing in the profile folder is opened, read or listed.
- Tested with a fake HTTP server on `127.0.0.1` (answers, never answers, wrong answer, port taken) and a fake Edge
  launcher. No real Edge in unit tests.

## Alternatives considered
- `--remote-debugging-port=0` and read `DevToolsActivePort`: reads the profile. Rejected.
- Read Edge's stderr for "DevTools listening on": no profile access, but depends on stderr staying open and on the
  wording. Rejected.
- A fixed port: clashes with other programs and is easier for them to find. Rejected.

## Consequences
- A short window exists between closing our socket and Edge binding the port; the retry covers it.
- The port is still random and on 127.0.0.1 only, so the ADR-002 consequence about other programs of the same user
  stays the same.
- The 10 s per attempt is a first guess. Slice 1 reports record each attempt's duration; changing it needs a new ADR.
