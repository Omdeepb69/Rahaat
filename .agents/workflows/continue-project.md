---
description: Resume work on the project from persistent state after a context reset or new session. Entry point for "keep going".
---

1. Read @/PROJECT_PLAN.md in full, especially the Status checklist, Current
   Task, and the most recent Log entries.
2. Read @/ARCHITECTURE.md for the stable decisions relevant to the current
   phase.
3. Skim @/LESSONS.md's titles for anything relevant to the current phase —
   same as `/implement-task` does per-task, just once here on resume.
4. If the Current Task section is empty or ambiguous, determine the next
   unblocked task from the Status checklist (first unchecked task whose
   `depends_on` are all checked off) and fill in Current Task before
   proceeding.
5. If the plan itself looks incomplete or stale for the stated Goal, run
   `/plan-project` first instead of guessing.
6. Otherwise, run `/implement-task`.
7. If a Log entry indicates an unresolved blocker from the previous
   session, address or report on the blocker before starting new work —
   don't silently skip past it.
