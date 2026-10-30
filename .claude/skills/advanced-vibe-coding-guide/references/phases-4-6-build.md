# Phases 4 to 6: Memory, first slice, feature loop

Contents: Phase 4 Project memory | Phase 5 First vertical slice | Phase 6 Feature loop

## Phase 4: Project memory (CLAUDE.md, rules, hooks)

- Goal: Claude remembers the rules every session without re-explaining.
- Artifact: `CLAUDE.md`, `.claude/settings.json`, `.claude/rules/`, `.claude/agents/`
- Gate: CLAUDE.md is short (under 150 lines) and reads like an index.

Key idea: CLAUDE.md is a table of contents, not a novel. One line per topic, pointing to the real docs. Claude reads the index, then opens only what it needs. Template: `assets/CLAUDE.md.template`.

Hooks = guarantees. Prompts = suggestions. If a rule must ALWAYS happen (format, test, block secrets), make it a hook.

Prompt A: CLAUDE.md and settings

```text
Create CLAUDE.md as a lean index, using docs/ as the source of truth.

Rules for CLAUDE.md:
- Under 150 lines. One line per topic, pointing to the real doc.
- Use plain file paths. Do not use @imports: they load the whole file at
  startup and do not save context.
- Keep only what Claude cannot guess from the code: commands, architecture
  rules, workflow rules, gotchas. For every line ask: would removing it
  cause a mistake? If not, cut it.

Then propose .claude/settings.json with:
- Deny rules for reading .env files and secrets folders,
  for example Read(./.env), Read(./.env.*), Read(./secrets/**)
- Deny rules for destructive commands, for example Bash(rm -rf *)
  and force pushes
- A PostToolUse hook (matcher Write|Edit) that runs the formatter
- A Stop hook that runs the FAST tests (unit only) and blocks the stop
  only when they fail

Show me the settings before saving.
Explain each rule and hook in plain English.
Tell me what these rules cannot protect against.
```

Prompt B: the two subagents

```text
Create two subagents in .claude/agents/:

1. code-reviewer
   - Tools: read-only only (Read, Grep, Glob). No Edit, no Write.
   - Reviews changes against docs/architecture.md, docs/adr/, and CLAUDE.md.
   - Reports only gaps that affect correctness, the plan, the acceptance
     criteria, or the architecture rules. Skips style preferences.
   - Output: findings ranked by severity, each with file and line.

2. test-writer
   - Writes tests from the acceptance criteria in docs/requirements.md.
   - Writes tests first. Never changes application code.

Show me both files before saving.
```

Tell the user about these limits, they are easy to miss:
- If a Stop hook keeps blocking, Claude Code ends the turn anyway after 8 consecutive blocks. Keep the test command fast and reliable.
- Deny rules are pattern matching, not a security boundary. Real secrets stay out of the project. Use read-only database credentials in dev.

Why it is written this way: a short index gets followed, a long one gets ignored. Plain paths are opened only when needed, while @imports load at startup. A reviewer with read-only tools cannot quietly fix and hide problems.

## Phase 5: First vertical slice

- Goal: one tiny feature working through ALL layers. Proves the architecture.
- Artifact: `docs/plans/plan-<feature>.md` + passing tests.
- Gate: the slice works end-to-end and tests pass.
- Example slice: create one record, save it, read it back, show it on screen.

Use the slice that Phase 2 recommended unless the user picks another.

Step 1. Plan (run in Plan Mode):

```text
Plan the smallest end-to-end feature that proves the architecture:
[e.g. create a habit, save it, list it on the home screen].

Read docs/requirements.md, docs/architecture.md, and docs/adr/ first.

Write docs/plans/plan-<feature>.md with:
- Goal, and what is OUT of scope for this slice
- Files to create or change, and why
- Data flow through each layer
- Acceptance criteria from requirements.md (quote the story IDs)
- Tests to write first
- One end-to-end check that proves it works
- Risks and open questions

If the plan conflicts with the architecture or an ADR, say so.
Do not choose silently.

Do not implement yet. Stop and wait for my notes.
```

Step 2. Annotate. The user opens the plan file and adds notes directly in it, like `> NOTE: use PATCH not PUT`, then sends:

```text
Address all my notes in the plan. Don't implement yet.
```

Repeat until nothing is left to fix. In Plan Mode, Ctrl+G opens the plan in the user's text editor.

Step 3. Build (only after the plan is approved):

```text
Implement the approved plan in docs/plans/plan-<feature>.md.

First, create a branch named feature/<feature>.

Order:
1. Write failing tests from the acceptance criteria. Run them and show
   that they fail.
2. Implement until the tests pass.
3. Run lint, typecheck, and the full test suite. Paste the real output.
4. Show me the diff summary.

Rules:
- Follow CLAUDE.md. Touch only files listed in the plan.
- Never edit a test just to make it pass. If a test is wrong, tell me.
- No new dependencies without asking.
- Do not commit. I review the diff first.
- If something unexpected comes up, stop and tell me instead of improvising.
```

Step 4. Review:

```text
Run git diff --name-only against main and give that file list to the
code-reviewer subagent. Ask it to review the changes against
docs/plans/plan-<feature>.md, docs/architecture.md, and CLAUDE.md.

Report only gaps that affect correctness, the plan, or the architecture rules:
layer violations, duplicated logic, missing tests, security issues,
and anything changed outside the plan's scope.
Skip style preferences. Rank by severity. Do not edit files.
```

Step 5. The user reviews the diff themselves, then commits.

Why it is written this way: stating what is out of scope plus one end-to-end check makes the plan testable. Watching tests fail first proves they test something. Pasted output is evidence, "tests pass" is only a claim. Forbidding test edits stops Claude from passing by weakening the tests. A reviewer in a fresh context judges the result on its own terms.

## Phase 6: Feature loop (repeat for every feature)

Use the Phase 5 plan, build, and review prompts for every new feature.

```text
New branch
   -> Plan (Plan Mode) -> annotate -> approve
   -> Tests first -> implement -> verify
   -> Reviewer subagent
   -> You review the diff
   -> Commit -> PR -> merge
   -> /clear -> next feature
```

Rules in the loop:
- One feature per branch, one feature per session.
- If Claude makes the same mistake twice, add it to CLAUDE.md "Gotchas".
- If a decision changes, write a new ADR first, then change code.
- For parallel work, use git worktrees so two Claude sessions do not collide. Start with two sessions max.
- Every few features, run the drift check:

```text
Audit the codebase against docs/architecture.md and docs/adr/.
Report, with file and line for each item:
- Layer violations
- Duplicated logic
- Files over 300 lines
- Dead code
- Dependencies not listed in docs/constraints.md
- Decisions visible in code that have no ADR
- Rules in CLAUDE.md that no longer match reality
Rank by risk. Do not fix anything yet.
```
