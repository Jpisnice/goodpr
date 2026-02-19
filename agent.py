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
            "ALWAYS call this subagent FIRST before writing any PR. "
            "It reads git patch text and returns: a PR title, a 2-4 sentence summary, "
            "a list of key files changed, and the main change types (feature/fix/refactor/docs). "
            "Do NOT write the PR without calling this first."
        ),
        "system_prompt": (
            "You are a specialist in summarizing git patches into concise, "
            "reviewer-friendly descriptions.\n\n"
            "You will receive the full patch text (git format-patch output) in your "
            "task. Analyze it and return your response in this EXACT format:\n\n"
            "TITLE: <one-line PR title>\n"
            "SUMMARY: <2-4 sentences describing what changed and why>\n"
            "FILES: <comma-separated list of the most important files changed>\n"
            "CHANGE_TYPES: <comma-separated labels: feature, fix, refactor, docs, test, chore>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [],
    }

    implications_subagent = {
        "name": "implications-agent",
        "description": (
            "ALWAYS call this subagent SECOND before writing any PR. "
            "It reads git patch text and returns: breaking changes, migration steps, "
            "dependency/config changes, testing evidence, and risk level. "
            "Do NOT write the PR without calling this first."
        ),
        "system_prompt": (
            "You analyze the impact and risk of code changes.\n\n"
            "You will receive the full patch text in your task. Analyze it and return "
            "your response in this EXACT format:\n\n"
            "BREAKING: <bullet list of breaking changes, or 'None'>\n"
            "MIGRATIONS: <bullet list of required migration steps, or 'None'>\n"
            "DEPS_CONFIG: <bullet list of dependency or config changes, or 'None'>\n"
            "TESTING: <bullet list of tests added/modified and coverage evidence, or 'None'>\n"
            "RISK: <low | medium | high>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [],
    }

    system_prompt = (
        "You are a PR generation assistant. You MUST follow these steps in order "
        "and MUST NOT skip any step:\n\n"
        "STEP 1 — MANDATORY: Call task(name='summary-agent', task='<paste the full "
        "patch text from BEGIN_PATCH_CONTEXT to END_PATCH_CONTEXT here>'). "
        "Wait for the result before proceeding.\n\n"
        "STEP 2 — MANDATORY: Call task(name='implications-agent', task='<paste the "
        "same full patch text here>'). "
        "Wait for the result before proceeding.\n\n"
        "STEP 3: Use the outputs from BOTH subagents to compose the final PR "
        "description in Markdown with these headings: ## Summary, ## Changes, "
        "## Breaking changes, ## Testing, ## Risks & roll-out.\n\n"
        "IMPORTANT: Do NOT write the PR description before completing STEP 1 and "
        "STEP 2. Skipping the subagent calls is not allowed. "
        "Your first action must always be a task() call to summary-agent."
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
