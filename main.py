from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env so GOOGLE_API_KEY is set before the agent runs

from agent import build_pr_agent
from langchain_core.messages import AIMessage, ToolMessage
from tools.git_tools import GitPatchError, get_patch_history

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

LOG = logging.getLogger("goodpr")

NETWORK_ERROR_MSG = (
    "Network error: cannot reach the Gemini API (getaddrinfo failed).\n"
    "  - Check your internet connection.\n"
    "  - If behind a proxy, set HTTP_PROXY / HTTPS_PROXY.\n"
    "  - Try another network or DNS (e.g. 8.8.8.8)."
)


def _content_repr(content: object, max_len: int = 500) -> str:
    if content is None:
        return "None"
    s = repr(content) if not isinstance(content, str) else content
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def setup_logging(log_path: Path) -> None:
    """Configure logging to the given file and to stderr at INFO."""
    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(logging.Formatter(fmt))
    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setLevel(logging.INFO)
    stderr_h.setFormatter(logging.Formatter(fmt))
    LOG.setLevel(logging.DEBUG)
    LOG.addHandler(file_h)
    LOG.addHandler(stderr_h)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a high-quality PR description from recent git commits."
    )
    parser.add_argument(
        "repo_path",
        help="Path to the local git repository to analyze.",
    )
    parser.add_argument(
        "--commit-offset",
        "-n",
        type=int,
        default=5,
        help="Number of commits back from HEAD to include (default: 5).",
    )
    parser.add_argument(
        "--thread-id",
        help="Optional thread id for the agent run; defaults to a derived UUID.",
    )
    parser.add_argument(
        "--log-file",
        "-l",
        default="goodpr.log",
        metavar="PATH",
        help="Log file path (default: goodpr.log in current directory).",
    )

    args = parser.parse_args()

    log_path = Path(args.log_file)
    setup_logging(log_path)
    LOG.info("Logging to %s", log_path)

    repo_path = args.repo_path
    commit_offset = args.commit_offset
    resolved_path = Path(repo_path).resolve()
    LOG.info("repo_path=%s commit_offset=%s", resolved_path, commit_offset)

    try:
        patch_context = get_patch_history(str(resolved_path), commit_offset)
    except GitPatchError as e:
        LOG.exception("Failed to generate git patch context")
        print(f"Failed to generate patch context: {e}", file=sys.stderr)
        sys.exit(1)

    LOG.info("Patch context length: %d chars", len(patch_context))

    # Write the patch to a file so subagents can read it without needing
    # the main agent to copy massive text into task() call arguments.
    patch_file = Path("patch_context.txt").resolve()
    patch_file.write_text(patch_context, encoding="utf-8")
    # Use forward slashes so the path survives intact through LLM tool call arguments
    # on Windows (backslashes get treated as escape sequences when the model serialises
    # the task() string and read_patch_file receives a mangled path).
    patch_file_posix = patch_file.as_posix()
    LOG.info("Patch written to %s", patch_file_posix)

    agent = build_pr_agent()

    thread_id = args.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    user_message = {
        "role": "user",
        "content": (
            f"Generate a professional pull request description in Markdown for the "
            f"last {commit_offset} commits in the repository at {resolved_path}.\n\n"
            f"The git patch has been saved to: {patch_file_posix}\n\n"
            "IMPORTANT: You MUST call task(name='summary-agent', ...) and "
            "task(name='implications-agent', ...) — pass the patch file path above "
            "in each task string. The subagents will read the file themselves. "
            "Only after receiving both outputs should you write the final Markdown PR. "
            "Do NOT skip the subagent calls and do NOT read the file yourself."
        ),
    }

    LOG.info("Invoking agent...")
    try:
        result = agent.invoke({"messages": [user_message]}, config=config)
    except (OSError, Exception) as e:  # noqa: BLE001
        if httpx and isinstance(e, httpx.ConnectError):
            LOG.exception("ConnectError calling Gemini API")
            print(NETWORK_ERROR_MSG, file=sys.stderr)
            sys.exit(1)
        err_msg = str(e).lower()
        if "getaddrinfo failed" in err_msg or "11002" in err_msg:
            LOG.exception("DNS/network error calling API")
            print(NETWORK_ERROR_MSG, file=sys.stderr)
            sys.exit(1)
        raise
    messages = result.get("messages", [])
    LOG.info("Result keys: %s; message count: %d", list(result.keys()), len(messages))

    def _get_ai_content(msg: object) -> str:
        """Extract a single string from an AIMessage (str, list of parts, or dict)."""
        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            for part in content:
                if isinstance(part, str) and part.strip():
                    return part.strip()
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text and str(text).strip():
                        return str(text).strip()
        return ""

    for i, msg in enumerate(messages):
        name = type(msg).__name__
        content = getattr(msg, "content", None)
        tool_calls = getattr(msg, "tool_calls", None)
        LOG.debug(
            "message[%d] %s content_type=%s content_len=%s tool_calls=%s",
            i,
            name,
            type(content).__name__,
            len(content) if isinstance(content, str) else (len(content) if content else 0),
            len(tool_calls) if tool_calls else 0,
        )
        LOG.debug("message[%d] content preview: %s", i, _content_repr(content))
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "?")
            LOG.debug("ToolMessage[%d] name=%s content_len=%s", i, tool_name,
                      len(content) if isinstance(content, str) else 0)
        if isinstance(msg, AIMessage):
            txt = _get_ai_content(msg)
            LOG.info("AIMessage[%d] extracted length=%d tool_calls=%s", i, len(txt), bool(tool_calls))

    pr_markdown = ""

    # Prefer the last AI message with non-empty content (the final reply)
    for idx, msg in enumerate(reversed(messages)):
        i = len(messages) - 1 - idx
        if isinstance(msg, AIMessage):
            txt = _get_ai_content(msg)
            if txt:
                pr_markdown = txt
                LOG.info("Using AIMessage at index %d (length %d)", i, len(txt))
                break
        elif isinstance(msg, dict) and msg.get("type") == "ai":
            txt = (msg.get("content") or "").strip()
            if txt:
                pr_markdown = txt
                LOG.info("Using dict AI message at index %d", i)
                break

    # Fallback: if no last AI had content (e.g. last was tool_calls only), use longest AI content
    if not pr_markdown:
        candidates = []
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage):
                txt = _get_ai_content(msg)
                if txt:
                    candidates.append((i, txt))
        if candidates:
            candidates.sort(key=lambda p: -len(p[1]))
            pr_markdown = candidates[0][1]
            LOG.info("Using longest AIMessage at index %d (fallback, length %d)", candidates[0][0], len(pr_markdown))

    if not pr_markdown:
        type_names = [type(m).__name__ for m in messages]
        LOG.warning(
            "No PR content extracted. Messages: %s",
            type_names,
        )
        print(
            "No PR description was produced. Check that the agent completed (no errors). "
            f"Total messages: {len(messages)}; types (last 5): {type_names[-5:]}. "
            f"Details in log: {log_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(pr_markdown)


if __name__ == "__main__":
    main()
