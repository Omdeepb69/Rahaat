# Lessons

A distilled reasoning library, not a log. `PROJECT_PLAN.md`'s Log records
*what happened, in order* — this file records *what would help on a
different task*, retrievable by relevance instead of by reading
chronologically.

Inspired by the ReasoningBank pattern (Ouyang et al., "ReasoningBank:
Scaling Agent Self-Evolving with Reasoning Memory," arXiv:2509.25140) and
the post-run half of what runtime tools like ReasonBlocks do — extract a
reusable lesson after a task, retrieve the relevant one before the next.
This file replicates the distill-and-retrieve idea; it can't replicate
mid-run interception, which needs a runtime wrapper, not a markdown file.

## What belongs here

A lesson is **generalizable** — it should plausibly help on a task in a
*different* part of the codebase, or even a different project entirely.
If a note only makes sense re-reading this exact task's diff, it belongs
in `PROJECT_PLAN.md`'s Log, not here.

Good lesson: "HF's `Cache.update()` must return `(k, v)` for the current
layer only, not the accumulated cache — easy to get backwards."

Not a lesson (belongs in the Log instead): "Implemented `SimpleKVCache` in
`minigen/cache.py`."

## Format

Each entry: a short title, then 2-4 lines — what happened, what the
generalizable takeaway is, and where it applies. Keep entries short; a
lesson that takes a paragraph to state usually hasn't been distilled
enough yet.

Order: newest first, so skimming from the top surfaces recent lessons
first without needing to search.

---

## Pytest entrypoint collisions from ambient ROS environment
- What happened: pytest failed during initial collection because `PYTHONPATH` contained `/opt/ros/jazzy/lib/python3.12/site-packages`, triggering setuptools entrypoint loading for `launch_testing` which failed on missing dependencies.
- Takeaway: In hybrid development environments where ROS or robotics paths leak into `PYTHONPATH`, pytest must be shielded with `addopts = "-p no:launch_testing"` in `pyproject.toml` and pytest invoked with clean `PYTHONPATH`.
- Applies to: Any Python project running tests on systems with ROS or other system-level pytest plugin injectors.
