# Skills

This folder is intentionally empty in the template. Skills are
project/domain-specific — CUDA specifics, a particular ML framework,
benchmarking methodology, your own team's testing conventions — and putting
them here up front would make this template project-specific, which
`AGENTS.md` explicitly says to avoid.

## Convention

Each skill is its own folder with a `SKILL.md`:

```
.agents/skills/
├── <skill-name>/
│   └── SKILL.md
```

`SKILL.md` needs YAML frontmatter with at minimum a `description` — the
agent sees only the name + description at session start (discovery), and
loads the full file only when a task looks relevant (activation). Keep the
description specific enough to trigger correctly and keep the body focused;
skills are meant to stay out of context until they're actually needed.

## When to add one here vs. put it in AGENTS.md

- Goes in `AGENTS.md` / `.agents/rules/`: universal, always relevant,
  behavioral ("how an agent should act").
- Goes in a skill: specialized knowledge only relevant to specific tasks
  ("how CUDA memory pooling works in this codebase", "how we benchmark",
  "the house style for API docs"). If loading it for every task would just
  be noise, it's a skill, not a rule.
