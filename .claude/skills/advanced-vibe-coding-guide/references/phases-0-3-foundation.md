# Phases 0 to 3: Foundation

Contents: Phase 0 Setup | Phase 1 Requirements | Phase 2 Architecture + ADRs | Phase 3 Skeleton

## Phase 0: Setup the workspace

- Goal: clean, safe workspace before Claude touches anything.
- Artifact: empty git repo with a first commit.
- Gate: `git status` is clean. No real secrets anywhere.

The user does this part (no prompt):
- `git init`, create a `main` branch, make a first commit.
- Create `.gitignore` with `.env` in it.
- Permissions: start in a mode where Claude asks before it edits files or runs commands. Pre-approve only safe, repeatable commands (tests, lint) with `/permissions`. Do not approve everything.
- Never give Claude live production credentials.

## Phase 1: Requirements (the spec)

- Goal: turn the idea into clear, testable requirements.
- Artifact: `docs/requirements.md`
- Gate: every feature has acceptance criteria the user understands.
- Role to adopt: senior business analyst. Interview first, write second. No architecture, no code.
- Why a spec first: without one, AI amplifies ambiguity instead of resolving it.

Fill in the project idea from what the user told you. If they gave none, ask for it in one question.

```text
Interview me before writing anything.

Project idea:
[Describe the app in plain words: who uses it, what problem it solves.]

Use the AskUserQuestion tool (or plain chat if it is unavailable).
Ask one group of questions at a time about:
- Users and roles
- Core features for version 1 (MVP)
- What is explicitly OUT of scope for version 1
- Data the system stores
- External systems it must connect to
- Non-functional needs: performance, security, offline, scale

Do not ask obvious questions. Dig into the hard parts I may not have
considered: edge cases, failure cases, and tradeoffs.
Keep interviewing until every group is covered.

Then write docs/requirements.md with:
1. Problem statement
2. Users and roles
3. MVP features as numbered user stories (US-01, US-02, ...)
4. Acceptance criteria per story (Given / When / Then)
5. Out of scope list
6. Assumptions you made, so I can correct them
7. Open questions

Rules:
- Plain language. Explain any jargon in one line.
- Do not design architecture. Do not write code.
- Stop after writing the file and wait for my approval.
```

Why it is written this way: the interview forces decisions before any code. Numbered stories (US-01) let later plans and tests point back to a requirement. Listing assumptions lets the user correct them early.

After approval: tell the user to start a fresh session for Phase 2.

## Phase 2: Architecture + decisions

- Goal: simplest maintainable design, explained so the user understands it.
- Artifact: `docs/architecture.md`, `docs/constraints.md`, `docs/workflows.md`, `docs/adr/ADR-001...`
- Gate: the user can explain the data flow of one feature out loud. Ask them to do it.
- Role to adopt: senior software architect helping a beginner. Plain English, simplest design that fits.

Step 1. Run in Plan Mode. Ask for the preferred technology if not known.

```text
Read docs/requirements.md. If code already exists, read it before proposing
anything.

Preferred technology: [JavaScript/TypeScript, Python, or "recommend one"]

Tasks:
1. Recommend the technology and explain why in plain English.
2. Recommend the SIMPLEST architecture that fits the current requirements
   and realistic growth. Every layer must have a reason to exist.
   If the project is small, drop layers and say which ones and why.
3. Show an architecture diagram (text).
4. Propose the folder tree.
5. Explain each folder's responsibility.
6. Define dependency rules (who may call whom).
7. Walk through one feature from UI to storage.
8. List risks: circular dependencies, duplicated logic, oversized files,
   tight coupling, vendor lock-in.
9. List each major decision as an ADR candidate
   (state management, database, auth, hosting).
   Recommend one option per decision. Mention alternatives only where the
   choice is hard to reverse.
10. Recommend the smallest first vertical slice that proves the architecture.
11. Propose implementation phases.

Rules:
- Do not write code or create files yet.
- Do not use a pattern just because it is popular.
- Keep business logic out of UI and database code.
- External systems must sit behind a connector layer.
- Prefer official SDKs over hand-written HTTP calls when a maintained SDK exists.
- State assumptions instead of asking, unless critical info is missing.

Stop after presenting the architecture and wait for my approval.
```

Step 2. Only after the user approves the architecture:

```text
The architecture is approved. Write it down:
- docs/architecture.md (diagram, layers, dependency rules, example flow)
- docs/constraints.md (stack, versions, approved libraries, limits)
- docs/workflows.md (user flow and data flow for each MVP story)
- docs/glossary.md
- docs/adr/ADR-001-<topic>.md, one file per decision, using this format:
  Title / Status / Date / Context / Decision / Alternatives considered /
  Consequences

Rules:
- Check current stable versions with the package manager or official docs.
  Do not guess version numbers.
- One decision per ADR. Keep each ADR under one page.
- Do not create source code.
- Show me the files when done.
```

ADR format: see `assets/ADR.template.md`. Status is one of Proposed, Accepted, or Superseded by ADR-0xx. ADRs stop Claude from silently switching patterns later.

Why it is written this way: asking for the simplest design, and permission to drop layers, stops over-engineering. The first-slice recommendation feeds Phase 5. Versions come from the package manager, not from memory.

Target project structure: see `assets/project-structure.txt`. It is a starting shape, not a law. Claude should simplify it for small projects.

## Phase 3: Skeleton

- Goal: folders and empty files only.
- Artifact: the folder tree in git.
- Gate: tree matches `docs/architecture.md`. No application logic anywhere, only empty files and framework init files.

```text
Create the project skeleton only, from the approved docs/architecture.md.

Allowed:
- Inspect the repo
- Create the approved folders and empty files
- A .gitkeep file in folders that would otherwise be empty
  (git does not track empty folders)
- Minimum framework init files, only if the project does not exist yet

Not allowed:
- Application code, imports, comments, TODOs, placeholder classes
- Installing extra packages
- Database setup, tests, config changes
- Files not in docs/architecture.md
- Overwriting existing non-empty files

After:
1. Show the final tree
2. List created, preserved, and skipped files
3. Confirm no implementation code was added

Stop. Do not start the next phase.
```

Then the user commits: `git commit -m "chore: project skeleton"`

Why it is written this way: git ignores empty folders, so `.gitkeep` makes the tree real. The final stop line keeps Claude from rolling into Phase 4.
