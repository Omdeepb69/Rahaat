---
description: Routing and enforcement for specialized creative engineering skills (Frontend Design and Manim Video).
trigger: always_on
---

# Creative Engineering Skills Routing

Before starting work on specialized frontend or animation tasks, check the installed skills under `@/.agents/skills/`:

## 1. Frontend Engineering
For tasks involving:
- React, Next.js, Vite, Vue, or frontend applications
- HTML, CSS, Tailwind, or UI component architecture
- User interfaces, responsive layouts, and accessibility (WCAG AA)
- Design systems, animations, micro-interactions, and visual hierarchy

Read and follow `@/.agents/skills/frontend-design/SKILL.md` before implementing the solution:
- Avoid generic AI aesthetic (purple gradients, default rounded cards, uncurated typography).
- Define clear typographic hierarchy (e.g. Geist, Instrument Sans, Plus Jakarta Sans, DM Sans) and purposeful design tokens.
- Maintain atomic component architecture and single responsibility.
- Verify the result in a real browser whenever browser tools are available.

## 2. Mathematical & Technical Animation
For tasks involving:
- 3Blue1Brown-style cinematic explanations
- Mathematical visualizations, coordinate transforms, and geometric proofs
- Algorithm and computer science walkthroughs
- Architecture diagrams and technical explainer videos

Read and follow `@/.agents/skills/manim-video/SKILL.md` before implementation:
- Use Manim Community Edition via the dedicated `animations/` Python environment (`uv run manim`).
- Follow the pedagogical standard: geometry before algebra, opacity layering, purposeful breathing room (`self.wait()`), and cohesive visual language.
- Never claim a video is complete until it has rendered and verified successfully.

## 3. Separation of Concerns
- Do not use Manim for standard web interface animations; use CSS/Tailwind/Framer Motion.
- Do not use web frameworks to replace Manim when programmatic video rendering is requested.
- For tasks involving both, keep the toolchains clean and decoupled.

