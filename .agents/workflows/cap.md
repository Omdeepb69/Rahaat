---
description: "Scaffold a new project with the full agent system: AGENTS.md, PROJECT_PLAN.md, ARCHITECTURE.md, LESSONS.md, LEARNING.md, .agents/rules, .agents/workflows, .agents/skills. Usage: /cap <project_name>"
---

1. Take `<project_name>` from the invocation. If missing, ask for it before
   doing anything else.
2. Create a new directory named `<project_name>` (or confirm the current
   directory is the intended target if already empty and named correctly —
   ask if ambiguous).
3. Copy the following template structure into it, unmodified except where
   noted:
   ```
   <project_name>/
   ├── AGENTS.md
   ├── PROJECT_PLAN.md
   ├── ARCHITECTURE.md
   ├── LESSONS.md
   ├── LEARNING.md
   └── .agents/
       ├── rules/
       │   ├── 00-engineering.md
       │   └── 01-large-tasks.md
       ├── workflows/
       │   ├── plan-project.md
       │   ├── implement-task.md
       │   ├── continue-project.md
       │   ├── cap.md
       │   ├── ask.md
       │   ├── investigate.md
       │   ├── critic.md
       │   ├── red-team.md
       │   ├── brainstorm.md
       │   └── learn.md
       └── skills/
           └── README.md
   ```
4. In `PROJECT_PLAN.md`, fill in the Goal section with a one-line
   description of `<project_name>` if the user provided one at invocation
   time; otherwise leave the placeholder for `/plan-project` to fill in
   later.
5. Do not invent phases, tasks, or architectural decisions during
   scaffolding — leave `PROJECT_PLAN.md`'s phase breakdown,
   `ARCHITECTURE.md`'s sections, `LESSONS.md`, and `LEARNING.md` as
   placeholders/empty. That's `/plan-project`'s, `/implement-task`'s, and
   `/learn`'s job, not this workflow's — a fresh project has no lessons
   or learning history yet by definition.
6. Report the created structure and tell the user to run `/plan-project`
   next to actually decompose the work.
