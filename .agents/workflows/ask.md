---
description: "Answer a quick question directly and cheaply, without the full engineering ceremony. Usage: /ask <question>"
---

This workflow exists because not every question is a task. Most of
`AGENTS.md` (Before You Code, Verification, Definition of Done) is
calibrated for changes to a codebase — applying it to "wait, what does
this function actually do" wastes tokens and your time.

1. Answer the question directly, using what's already in context first.
2. Only read a file if the question genuinely can't be answered without
   it — one targeted read, not repository exploration.
3. Do not update `PROJECT_PLAN.md`, `ARCHITECTURE.md`, or `LESSONS.md` for
   this. A quick question is not a task or a lesson.
4. Do not pad the answer with caveats, restating the question, or
   "before I answer, let me first..." framing. Answer, then stop.
5. If the question turns out to actually require exploration, a decision,
   or a real change once you start — say so and ask whether to switch to
   a normal task, rather than quietly doing the full-weight version
   anyway.
