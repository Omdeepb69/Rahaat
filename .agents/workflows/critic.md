---
description: "Give a brutally honest, unhedged critique of code, a design, or a decision. Usage: /critic <what to critique>"
---

The point of this workflow is to say the true thing even when it's
unwelcome, not to find something nice to say first. If the honest verdict
is "this is fine," say that plainly too — brutal honesty cuts both ways,
it isn't a mandate to always find fault.

**Known limitation, stated up front:** if the code being critiqued was
written earlier in this same conversation, self-critique is measurably
less reliable than an independent review — models tend to under-critique
their own recent output. If this critique actually matters (a real
architectural decision, something about to ship), run this in a fresh
session/conversation instead of immediately after writing the thing. This
workflow still does its best in-session, but that limitation is real, not
a formality.

1. Actively disregard the reasoning that produced this — evaluate the
   artifact (code/design/decision) as if a stranger handed it to you,
   not as a continuation of your own prior thinking.
2. Do not sandwich the critique between compliments. No "overall this is
   solid, but..." — lead with the verdict.
3. Structure findings as: **Claim** (what's being asserted or done) →
   **Reality check** (is that actually true/sound?) → **Consequence**
   (what breaks, degrades, or becomes technical debt if this ships
   as-is).
4. Rank findings by actual severity — don't flatten a naming nitpick and
   a genuine correctness bug to the same weight.
5. If the honest answer is "this is over-engineered," "this doesn't solve
   the stated problem," or "this was the wrong approach from the start,"
   say exactly that, not a softened version of it.
6. No hedging language ("might", "could potentially", "it's possible
   that") on things you're actually confident about. Say what you think
   is true. Hedge only where you're genuinely uncertain, and say why.
7. End with a one-line verdict: ship it, fix these specific things first,
   or rethink the approach. Don't leave the verdict implicit in a list of
   observations.
8. If this critique surfaces the same category of issue you've flagged
   before on this project, note that explicitly — a repeated pattern is
   worth a `LESSONS.md` entry (see `.agents/rules/01-large-tasks.md`)
   more than a one-off does, since it points at a standing blind spot
   rather than a single mistake.
