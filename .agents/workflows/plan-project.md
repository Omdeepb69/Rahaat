---
description: Explore the repository and produce a full task decomposition in PROJECT_PLAN.md. Does not write or modify source code.
---

1. Read @/AGENTS.md and @/ARCHITECTURE.md in full before doing anything else.
2. Explore the repository to understand current structure and state. Do not
   modify source code during this workflow.
3. Confirm or ask for the project's goal if `PROJECT_PLAN.md`'s Goal section
   is empty or unclear.
4. Decompose the work into phases, and each phase into tasks, following
   `AGENTS.md`'s Large Task Decomposition rule: coherent architectural
   units, not arbitrary line/file boundaries, not whole features in one
   task.
5. For each task, define: objective, dependencies (by task ID), scope,
   constraints, and a concrete verification criterion — per the task
   template already in `PROJECT_PLAN.md`.
6. Mark explicit `depends_on` relationships between tasks so dependent work
   is never scheduled ahead of what it needs.
7. Write the full decomposition into `PROJECT_PLAN.md` — Status checklist,
   phase/task breakdown, and the first Current Task fully specified.
8. If any architectural decisions were made or assumed while planning
   (e.g. "backends go behind an Executor protocol"), record them in
   `ARCHITECTURE.md`, not just in the plan.
9. Do not implement anything. Stop after `PROJECT_PLAN.md` and
   `ARCHITECTURE.md` are written, and summarize the plan for review.
