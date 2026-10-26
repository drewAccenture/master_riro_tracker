# Habits, session hygiene, failure patterns

Load this when the user is stuck, Claude is misbehaving, or they ask how to work day to day.

## The 7 habits

1. Explore, Plan, Code, Verify, Commit. Always in this order. Skip the plan only when the whole change fits in one sentence.
2. Use Plan Mode for anything touching more than 2 to 3 files. Shift+Tab until the status bar shows plan mode, or start with `claude --permission-mode plan`. Claude can read but cannot edit.
3. Give Claude a way to check its own work, and ask for the evidence (pasted test output, not "it passes").
4. Context is the scarcest resource. Fresh session per task. `/compact` at milestones, `/clear` between unrelated tasks. If Claude was corrected twice on the same thing, or loops and forgets rules, `/clear` and restart with a better prompt.
5. One task per prompt.
6. Write decisions down. If it is not in a doc, Claude will re-decide it next week.
7. Commit often. Every approved step gets a git commit.

## Session hygiene

| Situation | Do |
|---|---|
| New unrelated task | `/clear` |
| Long session, milestone reached | `/compact`, commit |
| Claude loops, forgets rules, cites missing files | Stop. Commit. New session. |
| Corrected Claude twice on the same thing | `/clear`, restart with a better prompt |
| Spec or plan just approved | Fresh session to execute it |
| Big search / noisy test run | Use a subagent, ask for a short summary |
| Risky multi-file change | Plan Mode first |
| Want to undo | `/rewind` (Esc twice) for Claude's file edits, git for everything else |
| Same mistake twice | Add to CLAUDE.md Gotchas |

Checkpoints only track changes made through Claude's file editing tools. Bash changes are not captured, so git is the real undo button.

## Common failure patterns

- Builderitis: AI recreates things that already exist. Tell it to search first.
- Kitchen-sink sessions: unrelated tasks pollute context.
- Bloated CLAUDE.md: too long, half gets ignored.
- Saying yes to every permission.
- Mocked integrations never tested for real: they break at go-live.
- Mixed AI tools with no shared rules: shared CLAUDE.md + ADRs fix this.
- Trusting "done": verify with tests and your own eyes.
- Tests edited to pass: Claude changes the test instead of the code.
- Unscoped "investigate": fills the context. Scope it or use a subagent.
