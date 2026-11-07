---
description: Always-on universal engineering rules for this project.
trigger: always_on
---

Follow @/AGENTS.md for all engineering decisions, code style, testing,
verification, and behavioral rules. It is the single source of truth for
"how to engineer software" in this repository — do not duplicate or
re-derive its rules elsewhere; if something here conflicts with it,
`AGENTS.md` wins.

Also read @/ARCHITECTURE.md before touching existing code. It records
stable architectural decisions (module boundaries, interfaces, what may
depend on what) that `AGENTS.md`'s Repository Reality and Boundaries
sections require you to respect.

`@/LESSONS.md` holds distilled, generalizable lessons from past tasks —
distinct from `PROJECT_PLAN.md`'s Log, which is chronological project
history. `/implement-task` and `/continue-project` already check it at
the right points; you don't need to read it on every turn outside those
workflows.

`@/LEARNING.md` tracks the human's understanding of this codebase, not
the codebase's own state — a different axis entirely from the three files
above. Only `/learn` reads and writes it; don't reference it in ordinary
implementation work.

Additional workflows beyond the core plan/implement/continue loop:
`/ask` (quick low-ceremony questions), `/investigate` (root cause
analysis, no fix), `/critic` (brutal unhedged critique), `/red-team`
(systematic failure-mode attack), `/brainstorm` (divergent-then-convergent
ideation), `/learn` (Socratic curriculum against `LEARNING.md`). Use the
one that matches what's actually being asked instead of defaulting to
full implementation mode for everything.
