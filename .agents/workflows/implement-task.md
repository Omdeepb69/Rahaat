---
description: Implement exactly the Current Task in PROJECT_PLAN.md, verify it, and update the plan. Does not start the next task.
---

1. Read @/AGENTS.md, @/ARCHITECTURE.md, and the Current Task section of
   @/PROJECT_PLAN.md.
2. Skim @/LESSONS.md's titles (newest first). If 1-2 entries are genuinely
   relevant to this task's domain, keep them in mind while implementing.
   Most tasks won't have a relevant entry — that's normal, don't force a
   connection that isn't there.
3. Confirm the task's `depends_on` list is fully checked off in the Status
   section. If not, stop and report the blocker instead of proceeding.
4. Follow `AGENTS.md` §3 Before You Code: inspect the relevant module
   boundaries, read existing implementation and tests, trace callers before
   touching any public interface, check whether this already exists.
5. Implement only the Current Task's stated scope. Do not expand into
   adjacent work, even if it looks related or easy — see `AGENTS.md`'s
   Scope Discipline.
6. Run the task's stated verification criterion, plus `AGENTS.md` §17
   Verification (tests, type checking, linting, diff review) — whatever
   applies to this repository.
7. If verification fails: fix within the task's scope, or if the fix
   requires touching something outside scope, stop and report per
   `AGENTS.md`'s Stop and Ask rule rather than silently expanding scope.
8. If verification passes: update `PROJECT_PLAN.md` — check off the
   completed task, append a Log entry (per the Agent Handoff rule in
   `.agents/rules/01-large-tasks.md`), and fill in the next Current Task
   from the plan's existing decomposition.
9. If completing this task revealed that the plan's decomposition needs
   revision (a task was wrong-sized, a dependency was missed), update
   `PROJECT_PLAN.md` to reflect that explicitly — don't just quietly work
   around it.
10. If this task surfaced something genuinely generalizable — a mistake
    that cost real time, a non-obvious constraint of a library/API, a
    wrong assumption that had to be corrected — add one entry to
    `LESSONS.md` per its format. Skip this step if nothing from this task
    would actually help on a *different* task; not every task produces a
    lesson, and padding the file with routine work defeats its purpose.
11. Stop. Do not start the next task automatically, even if context budget
    remains — that's a separate invocation.
12. Summarize what changed, what was verified, and what's next.
