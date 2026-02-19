from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from tools.patch_retriever import build_patch_index, make_search_tool


def build_pr_agent(patch_path: str | None = None):
    """
    Create the Deep Agent configured for PR generation from git patch history.

    - Uses Gemini via the `google_genai:gemini-3-flash-preview` identifier.
    - The full git patch is written to disk; an in-memory BM25 index is built
      over that patch and exposed via a `search_patch(query, k)` tool.
    - Subagents ONLY access patch content through `search_patch` (no direct
      file reads or condensed views).
    - Loads the PR-writing skill from `skills/pr/`.
    """
    if patch_path:
        search_patch = make_search_tool(build_patch_index(patch_path))
    else:

        def search_patch(query: str, k: int = 5) -> str:
            return "Patch path not provided; search unavailable."

    summary_subagent = {
        "name": "summary-agent",
        "description": (
            "ALWAYS call this subagent FIRST before writing any PR. "
            "It analyzes git patch text via search_patch() and returns: a PR title, "
            "a 2-4 sentence summary, a list of key files changed, and the main change "
            "types (feature/fix/refactor/docs). "
            "Do NOT write the PR without calling this first."
        ),
        "system_prompt": (
            "You are a specialist in summarizing git patches into concise, "
            "reviewer-friendly descriptions.\n\n"
            "Your task string contains a file path to a git patch file that has "
            "already been indexed into an in-memory BM25 retriever. You MUST use "
            "search_patch(query='...') to explore this patch. Start by calling "
            "search_patch several times with different queries derived from the "
            "task (e.g. key modules, components, 'feature', 'fix', 'test', "
            "important filenames) to build an understanding of what changed.\n\n"
            "NEVER claim that the patch is truncated or that you cannot analyze it. "
            "If you need more detail about a specific file, function, or concept, "
            "refine your queries and call search_patch again.\n\n"
            "After gathering enough context, return your response in this EXACT format:\n\n"
            "TITLE: <one-line PR title>\n"
            "SUMMARY: <2-4 sentences describing what changed and why>\n"
            "FILES: <comma-separated list of the most important files changed>\n"
            "CHANGE_TYPES: <comma-separated labels: feature, fix, refactor, docs, test, chore>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [search_patch],
    }

    implications_subagent = {
        "name": "implications-agent",
        "description": (
            "ALWAYS call this subagent SECOND before writing any PR. "
            "It analyzes git patch text via search_patch() and returns: breaking "
            "changes, migration steps, dependency/config changes, testing evidence, "
            "and risk level. "
            "Do NOT write the PR without calling this first."
        ),
        "system_prompt": (
            "You analyze the impact and risk of code changes.\n\n"
            "Your task string contains a file path to a git patch file that has "
            "already been indexed into an in-memory BM25 retriever. You MUST use "
            "search_patch(query='...') to explore this patch. Call search_patch "
            "with targeted queries to discover:\n"
            "- Possible breaking changes (e.g. search_patch('breaking'), 'delete', 'remove', 'rename').\n"
            "- Migrations and data changes (e.g. 'migration', 'schema', 'migrate').\n"
            "- Dependency or config changes (e.g. 'pyproject.toml', 'package.json', 'env', 'config').\n"
            "- Tests and validation (e.g. 'test', 'spec', 'assert', 'e2e').\n\n"
            "Refine your queries as needed. NEVER claim that the patch is truncated "
            "or that you cannot analyze it; instead, issue more search_patch calls "
            "until you have enough evidence.\n\n"
            "Then return your response in this EXACT format:\n\n"
            "BREAKING: <bullet list of breaking changes, or 'None'>\n"
            "MIGRATIONS: <bullet list of required migration steps, or 'None'>\n"
            "DEPS_CONFIG: <bullet list of dependency or config changes, or 'None'>\n"
            "TESTING: <bullet list of tests added/modified and coverage evidence, or 'None'>\n"
            "RISK: <low | medium | high>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [search_patch],
    }

    system_prompt = (
        "You are a PR generation assistant. You MUST follow these steps in order "
        "and MUST NOT skip any step:\n\n"
        "STEP 1 — MANDATORY: The user message contains a file path to the git patch. "
        "Call task(name='summary-agent', task='Analyze the patch at <path> using search_patch "
        "to retrieve relevant chunks and summarize it.') where <path> is the exact file "
        "path from the user message. The subagent has a search_patch tool that queries "
        "an index built from this file; it MUST NOT try to read the file itself. "
        "Wait for the result before proceeding.\n\n"
        "STEP 2 — MANDATORY: Call task(name='implications-agent', task='Analyze the patch at <path> "
        "using search_patch to understand breaking changes, migrations, config/dependency changes, "
        "testing, and risk.') with the same file path. "
        "Wait for the result before proceeding.\n\n"
        "STEP 3: Use the outputs from BOTH subagents to compose the final PR "
        "description in Markdown with these headings: ## Summary, ## Changes, "
        "## Breaking changes, ## Testing, ## Risks & roll-out.\n\n"
        "IMPORTANT: Do NOT read the patch file yourself. Do NOT write the PR before "
        "completing STEP 1 and STEP 2. Your first action must be a task() call to summary-agent."
    )

    checkpointer = MemorySaver()

    agent = create_deep_agent(
        model="google_genai:gemini-3-flash-preview",
        system_prompt=system_prompt,
        subagents=[summary_subagent, implications_subagent],
        skills=["skills/pr/"],
        checkpointer=checkpointer,
    )

    return agent
