---
name: advanced-vibe-coding-guide
description: Runs a phased, gated workflow for building software with Claude Code instead of vibe coding (idea to requirements, architecture and ADRs, skeleton, CLAUDE.md and hooks, vertical slice, feature loop, integrations, hardening, go-live, maintenance). Use this skill whenever the user starts a new app, system, tool, or substantial feature, says "build me X" for anything bigger than a small script, asks which phase or what is next, asks for the prompt for a phase, or mentions requirements docs, architecture, ADRs, CLAUDE.md, hooks, subagents, plan mode, vertical slice, connectors, MCP, hardening, runbook, go-live, drift check, or "advanced vibe coding". Also use it when Claude Code sessions are going wrong (looping, forgetting rules, scope creep, tests edited to pass). Skip it for trivial one-line edits and one-off throwaway scripts.
---

# Advanced Vibe Coding Guide

The goal is to replace "tell Claude to build a system" with a process the user understands and controls.

The one rule: Claude designs, the user approves, Claude builds one small slice, a test proves it, then repeat. Every phase ends at a gate. The gate is where the user stays in control, so never skip one and never advance on your own.

## How to run this skill

1. **Find the phase.**
   - If you can see the repo (Claude Code), look for the artifacts in the phase map below. The first phase whose artifact is missing or stale is the current phase.
   - If you cannot see the repo (chat), ask one question: which phase are they in, or what exists already. Offer the phase list as options if you have a way to show options.
   - For a brand new idea, the phase is 0.
2. **Check the previous gate.** State it as a one-line check and confirm it is met. If it is not, say what is missing and stay on that phase. Do not hand out the next prompt.
3. **Load only the reference file for that phase** (see "Reference files"). Use its prompt as written. Fill only the bracketed placeholders, using what the user already told you. Ask for a missing placeholder in one short question. Do not rewrite prompts, merge phases, or add steps.
4. **Deliver the prompt.**
   - In chat: give the filled prompt in one code block, say whether to run it in Plan Mode, and give the gate to check afterwards. The prompt will be pasted into a Claude session that does not have this skill, so put the role line from the Roles table as the first line of the prompt.
   - Inside Claude Code: take the role from the Roles table yourself, silently, and run the prompt. Obey its own stop lines ("Stop and wait for my approval"). Do not announce or repeat the role.
5. **Stop at the gate.** After the user approves, give the next action only: the commit message, `/clear` or a fresh session if the reference file says so, and which phase comes next. Do not start it.

## Roles

The user should never have to type "Act as a senior...". Each phase below has a role. Take it when you reach the phase, and keep to its limits.

| Phase or task | Role | Role line (only when handing a prompt to a session without this skill) |
|---|---|---|
| 1 Requirements | Senior business analyst. Interview first, write second. No architecture, no code. | `Act as a senior business analyst.` |
| 2 Architecture | Senior software architect helping a beginner. Plain English, simplest design that fits. | `Act as a senior software architect helping a beginner.` |
| 8 Security audit | Security reviewer. Reports findings, never edits files. | `Act as a security reviewer.` |
| 5 Review, 4 subagents | The `code-reviewer` and `test-writer` subagents hold their own role in `.claude/agents/`. | none needed |

Other phases need no persona. Their prompts already carry the rules and stop lines.

## Phase map

| Phase | Name | Artifact to look for | Reference file |
|---|---|---|---|
| 0 | Setup the workspace | git repo, first commit, `.gitignore` | foundation |
| 1 | Requirements | `docs/requirements.md` | foundation |
| 2 | Architecture + ADRs | `docs/architecture.md`, `docs/adr/` | foundation |
| 3 | Skeleton | folder tree matching architecture, files empty | foundation |
| 4 | Project memory | `CLAUDE.md`, `.claude/settings.json`, `.claude/agents/` | build |
| 5 | First vertical slice | `docs/plans/plan-<feature>.md`, passing tests | build |
| 6 | Feature loop | one branch per feature, repeat Phase 5 prompts | build |
| 7 | Integrations | `src/connectors/<system>/`, ADR, contract tests | ship-and-maintain |
| 8 | Hardening | security checklist, e2e tests | ship-and-maintain |
| 9 | Go-live | `docs/runbook.md`, CI pipeline, release tag | ship-and-maintain |
| 10 | Maintain and evolve | changelog, postmortems, updated ADRs | ship-and-maintain |

For an existing project, skip phases whose artifacts already exist and are current. Start at the first missing one (for example, code exists but no `CLAUDE.md` means start at Phase 4).

## Rules that always apply

- **One phase at a time.** Never create files, add dependencies, or change decisions outside the current phase's allowed list. If something unexpected comes up, stop and tell the user instead of improvising.
- **Decisions go in ADRs.** If a decision changes, a new ADR comes first, then the code.
- **Verification is evidence.** Ask for pasted test output, not "it passes". Tests are never edited just to make them pass.
- **Plan Mode** for anything touching more than 2 to 3 files. Skip it only when the whole change fits in one sentence.
- **Context is scarce.** Suggest `/clear` between unrelated tasks, and a fresh session after a spec or plan is approved. After two failed corrections on the same issue, restart with a better prompt.
- **Hooks are guarantees, prompts are suggestions.** Anything that must always happen belongs in a hook.
- **Commit after each approved step.** Git is the real undo button.
- If the user asks for something that skips a phase ("just build it"), explain in one or two sentences what the skipped phase protects against, then offer the shortest safe path. The user decides.

## Style

Keep answers short and direct. Give the answer first, then the prompt or steps. Use numbered steps for procedures. Recommend one option and mention alternatives only when the choice is hard to reverse. Do not use em dashes. No filler, no praise.

## Reference files

Read the one that matches the phase. Each contains the goal, artifact, gate, ready-to-use prompts, and the reasoning behind them.

- `references/phases-0-3-foundation.md`: setup, requirements, architecture + ADRs, skeleton
- `references/phases-4-6-build.md`: CLAUDE.md + hooks + subagents, first vertical slice, feature loop, drift check
- `references/phases-7-10-ship-and-maintain.md`: integrations, hardening checklist, go-live, bug, incident, and refactor handling
- `references/habits-and-hygiene.md`: the 7 habits, session hygiene table, failure patterns. Read this when the user is stuck or Claude is misbehaving.

Templates in `assets/`: `CLAUDE.md.template`, `ADR.template.md`, `project-structure.txt`. Copy from them instead of rewriting from memory.
