---
description: "Investigate a bug or issue to find its actual root cause. Does not implement a fix. Usage: /investigate <issue description>"
---

Investigation is a separate activity from fixing. Jumping straight to a
patch usually fixes a symptom, not the cause — this workflow exists to
stop that.

1. Reproduce the issue if at all possible before theorizing about it. An
   unreproduced bug report is a hypothesis, not a confirmed fact.
2. Gather evidence: error messages/stack traces in full, the exact
   input/conditions that trigger it, recent changes to the relevant code
   (git log/blame on the affected area), and what the code was actually
   supposed to do per `ARCHITECTURE.md` or its own tests/docstrings.
3. Form multiple plausible hypotheses before testing any of them — do not
   commit to the first explanation that sounds right. A single hypothesis
   pursued to conclusion is confirmation bias, not investigation.
4. Test each hypothesis against the evidence and eliminate the ones that
   don't hold up. State explicitly which hypotheses were eliminated and
   why, not just which one "won."
5. Distinguish the root cause from the symptom. "The function returns
   None" is a symptom; "the cache lookup silently misses on a stale key
   because eviction doesn't update the index" is a root cause. If you
   can't state a mechanism, you don't have the root cause yet — keep
   investigating rather than reporting a guess as a finding.
6. Distinguish a real fix from a workaround. If the only available fix
   right now is a workaround, say so explicitly rather than presenting it
   as resolved.
7. Report: root cause (with mechanism), evidence that supports it,
   hypotheses ruled out, and severity/scope (what else might be affected
   by the same root cause elsewhere in the codebase).
8. Do not implement a fix as part of this workflow. If a fix is wanted
   next, that's a new task — hand off to normal implementation (via
   `/implement-task` if it's plan-tracked work) rather than silently
   patching inside the investigation.
