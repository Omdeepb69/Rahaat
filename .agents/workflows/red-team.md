---
description: "Systematically attack code or a design to find concrete failure modes, not judge its quality. Usage: /red-team <what to attack>"
---

Distinct from `/critic`: critic judges whether this was well-engineered.
Red-teaming doesn't judge — it attacks, mechanically, across a fixed set
of vectors, looking for ways this actually breaks.

Same limitation as `/critic` applies: attacking your own just-written code
in the same session is weaker than a fresh-session pass. Use a new
conversation for anything that actually matters.

Work through each vector explicitly — don't skip one because nothing
obvious comes to mind; "checked, nothing found" is a valid, useful result
for a vector, silence is not:

1. **Edge cases** — empty input, zero, negative, max size, single-element,
   duplicate entries, unicode/encoding, off-by-one boundaries.
2. **Malicious/adversarial input** — what happens with intentionally
   malformed, oversized, or crafted input? Injection surface if this
   touches shell commands, queries, or file paths.
3. **Concurrency/ordering** — what if this runs twice at once, or two
   calls race? What if operations arrive out of the order the code
   assumes?
4. **Resource limits** — what happens under memory pressure, at scale,
   with a slow/unavailable dependency, or when a timeout is hit mid-way?
5. **Wrong assumptions** — what does this code assume about its caller,
   its environment, or its inputs that isn't actually guaranteed anywhere?
   Trace each assumption to what enforces it — an unenforced assumption is
   a bug waiting for the day it's violated.
6. **Failure cascades** — if this specific thing fails, what else does it
   take down with it? Is the blast radius contained or does it propagate?
7. **Security/exposure** — does this leak anything (secrets, internal
   state, stack traces) to somewhere it shouldn't?

For each finding, report as: **Vector** → **Attack** (the specific
scenario) → **Result** (what actually happens) → **Severity**. Don't
report a theoretical concern as a finding without stating what concrete
input or scenario triggers it.
