---
description: How to handle work too large for one bounded agent context, and how to hand off state between sessions.
trigger: always_on
---

## Large Task Decomposition

When a task is too large to safely understand, implement, and verify within
one focused agent context:

1. Do not attempt the entire task in one pass.
2. Decompose it into independently understandable, implementable, and
   verifiable tasks.
3. Prefer coherent architectural units over arbitrary line/file boundaries.
   A task is the wrong size if it's either "the whole feature" or "rename
   one variable" — aim for "one abstraction, fully implemented and tested."
4. Record the decomposition in @/PROJECT_PLAN.md.
5. Each task must define: objective, dependencies, scope, constraints, and
   a verification criterion — see the task template in `PROJECT_PLAN.md`.
6. Implement one bounded task at a time.
7. Verify each task before marking it complete (see `AGENTS.md` §17
   Verification).
8. Update `PROJECT_PLAN.md` after each completed task — not at the end of
   the session, immediately after the task is verified.
9. Do not start an unrelated downstream task merely because context budget
   remains.
10. Never claim the parent task or phase is complete while incomplete
    subtasks remain.

The project plan is persistent state. Conversation history is not.

## Context Discipline

Do not load or reason over the entire repository when the current task has
a narrower dependency boundary.

Prefer, in order: the current task's contract in `PROJECT_PLAN.md` → the
specific files/interfaces it touches → their direct dependencies and tests
→ `ARCHITECTURE.md` for the relevant boundary → only then wider exploration.

Do not consume context with unrelated files, historical discussion, or
speculative architecture the current task doesn't need.

## Agent Handoff

When a task ends — whether completed, blocked, or the session is simply
ending — leave the repository in a state another agent can continue from
without this conversation's history.

Update `PROJECT_PLAN.md`'s Log with:

- what was completed
- files changed
- architectural decisions made (also add to `ARCHITECTURE.md` if the
  decision is meant to be stable/load-bearing, not just this task's detail)
- verification actually performed
- known limitations or deferred work
- the next task
- any unresolved blocker, stated plainly

Do not rely on conversation history as the record of project state. If it's
not in `PROJECT_PLAN.md`, it didn't happen as far as the next session is
concerned.
