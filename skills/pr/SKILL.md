---
name: goodpr_pr_writer
description: >
  High-quality pull request description writing for git repositories, based on
  commit history and patch diffs. Focuses on clear summaries, impact, risks, and
  testing information.
version: 0.1.0
---

## When to use this skill

- You have git patch context for a range of commits and must draft a pull request description.
- You need a professional, concise, and informative PR message in Markdown.

## What a good PR description looks like

1. **Title**
   - One line, clear and action-oriented.
   - Describe *what* changed and optionally *why*, not implementation details.

2. **Summary**
   - 2–4 sentences giving the high-level context:
     - Why this change was made.
     - What main capabilities or fixes it introduces.
   - Avoid low-level details that belong in commit messages.

3. **Detailed changes**
   - Bullet list capturing the most important changes.
   - Group related bullets (e.g. feature, refactor, infra, docs).
   - Reference key files or modules when helpful.

4. **Breaking changes / migrations**
   - Explicitly call out any breaking behavior.
   - If applicable, add a short “Migration” section with concrete steps.

5. **Dependencies / configuration**
   - Note added/removed dependencies, env vars, feature flags, or config keys.

6. **Testing**
   - Describe how the change was validated:
     - Automated tests (unit/integration/e2e) that were run.
     - Manual validation steps and environments.

7. **Risks or rollout notes**
   - Mention areas of elevated risk and how they are mitigated.
   - If useful, include rollout / fallback notes.

## Style guidelines

- Write for reviewers who have not read the code yet.
- Prefer short paragraphs and bullet lists over long walls of text.
- Be specific and concrete; avoid vague phrases like “misc fixes”.
- Use Markdown headings such as:
  - `## Summary`
  - `## Changes`
  - `## Breaking changes`
  - `## Testing`
  - `## Risks & roll-out`

## How to use this skill

When this skill is active:

1. Read the available git patch and any structured summaries.
2. Identify:
   - The main user-facing changes.
   - Important internal refactors worth mentioning.
   - Any breaking behavior, migrations, and dependency/config changes.
   - Evidence of testing and remaining risks.
3. Draft a Markdown PR description following the structure above.
4. Keep the tone professional and neutral; do not over-sell the change.

