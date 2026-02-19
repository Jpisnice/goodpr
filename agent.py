from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from tools.git_tools import condense_patch
from tools.patch_retriever import build_patch_index, make_search_tool


def read_patch_file(path: str) -> str:
    """Read and condense the git patch file so the result fits within the subagent
    context window without triggering DeepAgents' filesystem offload.

    The condenser keeps all commit headers, file stats, and @@ hunk headers verbatim,
    but truncates individual diff hunks to 30 lines. This preserves all information
    needed to write a quality PR description.

    Args:
        path: Absolute POSIX path to the patch file written by the orchestrator.
    """
    raw = Path(path).read_text(encoding="utf-8")
    return condense_patch(raw)


def build_pr_agent(patch_path: str | None = None):
    """
    Create the Deep Agent configured for PR generation from git patch history.

    - Uses Gemini via the `google_genai:gemini-3-flash-preview` identifier.
    - Patch context is provided directly in the user message.
    - Two subagents receive read_patch_file and search_patch tools; they load the
      patch (condensed) and can search the full patch for specific context.
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
            "It reads git patch text and returns: a PR title, a 2-4 sentence summary, "
            "a list of key files changed, and the main change types (feature/fix/refactor/docs). "
            "Do NOT write the PR without calling this first."
        ),
        "system_prompt": (
            "You are a specialist in summarizing git patches into concise, "
            "reviewer-friendly descriptions.\n\n"
            "Your task string contains a file path to a git patch file. "
            "Your FIRST action must be to call read_patch_file(path=<the path from your task>) "
            "to load a condensed overview of the patch (commit headers, file list, and truncated hunks). "
            "This overview is intentionally shortened; the full patch is available via search. "
            "You MUST then use search_patch(query='...') to look up specific files, modules, or "
            "keywords when you need detail (e.g. search_patch('page.tsx'), search_patch('API'), "
            "search_patch('test')). Do NOT respond that the file is truncated or that you cannot "
            "analyze — produce your output using the overview plus targeted search_patch calls. "
            "Then return your response in this EXACT format:\n\n"
            "TITLE: <one-line PR title>\n"
            "SUMMARY: <2-4 sentences describing what changed and why>\n"
            "FILES: <comma-separated list of the most important files changed>\n"
            "CHANGE_TYPES: <comma-separated labels: feature, fix, refactor, docs, test, chore>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [read_patch_file, search_patch],
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
            "Your task string contains a file path to a git patch file. "
            "Your FIRST action must be to call read_patch_file(path=<the path from your task>) "
            "to load a condensed overview of the patch (commit headers, file list, truncated hunks). "
            "This overview is intentionally shortened; the full patch is available via search. "
            "You MUST use search_patch(query='...') to look up specific files or topics when you "
            "need detail (e.g. search_patch('breaking'), search_patch('config'), search_patch('test'), "
            "search_patch('migration')). Do NOT respond that the file is truncated or that you cannot "
            "analyze — produce your output using the overview plus targeted search_patch calls. "
            "Then return your response in this EXACT format:\n\n"
            "BREAKING: <bullet list of breaking changes, or 'None'>\n"
            "MIGRATIONS: <bullet list of required migration steps, or 'None'>\n"
            "DEPS_CONFIG: <bullet list of dependency or config changes, or 'None'>\n"
            "TESTING: <bullet list of tests added/modified and coverage evidence, or 'None'>\n"
            "RISK: <low | medium | high>\n\n"
            "Keep your total response under 300 words. Do not add extra sections."
        ),
        "tools": [read_patch_file, search_patch],
    }

    system_prompt = (
        "You are a PR generation assistant. You MUST follow these steps in order "
        "and MUST NOT skip any step:\n\n"
        "STEP 1 — MANDATORY: The user message contains a file path to the git patch. "
        "Call task(name='summary-agent', task='Read the patch file at <path> and summarize it.') "
        "where <path> is the exact file path from the user message. "
        "The subagent has a read_patch_file tool and will load the file itself. "
        "Wait for the result before proceeding.\n\n"
        "STEP 2 — MANDATORY: Call task(name='implications-agent', task='Read the patch file at <path> and analyze its implications.') "
        "with the same file path. "
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
