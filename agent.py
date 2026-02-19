from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

def build_pr_agent():
    """
    Create the Deep Agent configured for PR generation from git patch history.

    - Uses Gemini via the `google_genai:gemini-2.5-flash-lite` identifier.
    - Patch context is provided directly in the user message.
    - Two subagents (no tools): summary-agent and implications-agent receive the
      entire patch content in the task string and analyze it using Gemini's
      large context window.
    - Loads the PR-writing skill from `skills/pr/`.
    """
    summary_subagent = {
        "name": "summary-agent",
        "description": (
            "Summarizes the git patch history into a clear PR title, high-level "
            "summary, key files changed, and main types of changes. Receives the "
            "full patch text in the task and should analyze it directly."
        ),
        "system_prompt": (
            "You are a specialist in summarizing git patches into concise, "
            "reviewer-friendly descriptions.\n\n"
            "You will receive the full patch text (git format-patch output) in your "
            "task. Use it to:\n"
            "- Propose a strong PR title.\n"
            "- Provide a 2–4 sentence high-level summary of what changed and why.\n"
            "- Identify the most important files or areas of the codebase touched.\n"
            "- Identify the main types of changes (feature, fix, refactor, docs, etc.).\n\n"
            "Respond with a concise summary suitable for the main agent to fold into "
            "a final PR description."
        ),
        "tools": [],
    }

    implications_subagent = {
        "name": "implications-agent",
        "description": (
            "Analyzes the git patches for breaking changes, migrations, dependency "
            "and configuration changes, testing evidence, and overall risk. Receives "
            "the full patch text in the task."
        ),
        "system_prompt": (
            "You analyze the impact and risk of code changes.\n\n"
            "You will receive the full patch text in your task. Look for:\n"
            "- Breaking or behavior-changing modifications.\n"
            "- Required migrations (DB schema, data, config keys, feature flags).\n"
            "- Dependency or infrastructure changes.\n"
            "- Added or modified tests and how thoroughly things were validated.\n"
            "- Any areas that are particularly risky.\n\n"
            "Return findings in concise bullet points that can be plugged into PR "
            "sections for breaking changes, migrations, testing, and risk."
        ),
        "tools": [],
    }

    system_prompt = (
        "You are a PR generation assistant using subagents.\n\n"
        "Workflow:\n"
        "1. The user message includes PATCH_CONTEXT between explicit markers.\n"
        "2. Delegate to `summary-agent` with the patch context in the task text.\n"
        "3. Delegate to `implications-agent` with the patch context in the task text.\n"
        "4. Combine the subagents' outputs into a single, well-structured PR "
        "   description in Markdown.\n\n"
        "Use headings like `## Summary`, `## Changes`, `## Breaking changes`, "
        "`## Testing`, and `## Risks & roll-out`. Keep the description focused on "
        "what matters for reviewers and downstream users.\n"
    )

    checkpointer = MemorySaver()

    agent = create_deep_agent(
        model="google_genai:gemini-2.5-flash-lite",
        system_prompt=system_prompt,
        subagents=[summary_subagent, implications_subagent],
        skills=["skills/pr/"],
        checkpointer=checkpointer,
    )

    return agent
