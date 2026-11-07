---
description: "Teach the actual repository through real assignments and Socratic questioning, tracked in LEARNING.md. Usage: /learn [topic, or blank for the next logical assignment]"
---

The goal is understanding that survives after the session ends, not a
good explanation in the moment — those aren't the same thing. Explaining
something well and having the person actually learn it are different
outcomes; this workflow optimizes for the second one, which means it will
sometimes feel slower than just being told the answer. That's the point,
not a flaw.

## Before starting

1. Read @/LEARNING.md's Standing Gaps and Confidence Map. Closing a
   flagged gap takes priority over opening new material, unless a topic
   was explicitly requested.
2. Read @/ARCHITECTURE.md's Module Map to find real, currently-existing
   parts of the repo to build the assignment around. Assignments must be
   grounded in actual files/functions in this codebase — not a generic
   exercise that happens to be adjacent to it.
3. If no topic was specified, pick the next assignment that would do the
   most to build a working mental model of the codebase — foundational
   concepts and core modules before edge-case/peripheral code, per
   `ARCHITECTURE.md`'s boundaries.

## Running the assignment

4. Give one concrete assignment tied to real code — not "explain how
   caching works" but "open `<real file>`, and before running anything,
   predict what `<real function>` returns for `<a specific input>`, and
   why." Prediction-before-reveal beats being told first; retrieval and
   committing to a guess is what makes it stick.
5. Ask questions rather than explain. If the person is stuck, use
   graduated hints — a gentle nudge first, a more specific pointer only
   if still stuck, and the direct answer only after a genuine attempt or
   if they explicitly ask to move on. Don't volunteer the answer early
   just to keep things moving; a wrong guess followed by a correction
   teaches more than being told upfront.
6. When they answer, don't just confirm or deny — ask them to justify it,
   or ask a follow-up that tests whether the understanding generalizes
   ("okay, so what would happen if this were called with an empty
   batch?") rather than accepting a right answer as proof of solid
   understanding on its own.
7. Assess honestly at the end of the assignment: Solid, Shaky, or
   Bluffing — based on what they actually demonstrated, not how much
   effort they put in or how close they got. A generous assessment here
   defeats the entire point of the file.

## After the assignment

8. Update `LEARNING.md`: append an Assignment Log entry, update the
   Confidence Map for the relevant topic, and add or remove a Standing
   Gaps entry as appropriate.
9. If the assignment revealed a gap, the follow-up in the Assignment Log
   should be a specific next assignment, not "review this more" — a
   vague follow-up is unactionable next session.
10. Stop after one assignment unless asked to continue. A learning session
    that tries to cover too much in one pass produces the same shallow
    "felt like I understood it" outcome this workflow exists to avoid.
