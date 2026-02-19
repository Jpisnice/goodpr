from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final


_MAX_PATCH_BYTES: Final[int] = 500_000  # ~500KB cap; Gemini 1M context can handle more

# DeepAgents offloads tool results that exceed ~20K tokens (~80KB at 4 chars/token).
# Keeping subagent-visible content well under this avoids the offload-to-preview problem.
_SUBAGENT_MAX_BYTES: Final[int] = 60_000

# Max diff lines to keep per @@ hunk before truncating. Commit metadata and file
# stats are always kept in full; only line-level diff content is cut.
_MAX_HUNK_LINES: Final[int] = 30


class GitPatchError(RuntimeError):
    """Raised when we cannot generate a patch from the target repository."""


def condense_patch(patch_text: str, max_bytes: int = _SUBAGENT_MAX_BYTES) -> str:
    """Return a condensed version of a git format-patch stream safe for subagent context.

    Strategy:
    - All commit headers (From / Date / Subject) are kept verbatim.
    - All file-stat lines (diff --git, ---, +++, @@) are kept verbatim.
    - Each diff hunk is truncated to _MAX_HUNK_LINES lines.
    - If the result still exceeds max_bytes a final hard truncation is applied.

    This preserves everything needed to write a quality PR description (what changed,
    which files, commit intent) without the raw line-by-line diff noise.
    """
    if len(patch_text) <= max_bytes:
        return patch_text

    # Split on the "From <sha> Mon Sep 17 ..." separator used by git format-patch.
    commit_blocks = re.split(
        r"(?=^From [0-9a-f]{40} Mon Sep 17)", patch_text, flags=re.MULTILINE
    )

    condensed_parts: list[str] = []
    for block in commit_blocks:
        if not block.strip():
            continue
        condensed_lines: list[str] = []
        hunk_line_count = 0
        in_hunk = False

        for line in block.splitlines():
            if line.startswith("@@"):
                # New diff hunk — always keep the @@ header itself.
                in_hunk = True
                hunk_line_count = 0
                condensed_lines.append(line)
            elif in_hunk and not (
                line.startswith("diff --git")
                or line.startswith("--- ")
                or line.startswith("+++ ")
                or line.startswith("From ")
                or line.startswith("Date:")
                or line.startswith("Subject:")
                or line.startswith("index ")
                or line.startswith("new file")
                or line.startswith("deleted file")
                or line.startswith("rename ")
                or line.startswith("similarity ")
            ):
                if hunk_line_count < _MAX_HUNK_LINES:
                    condensed_lines.append(line)
                    hunk_line_count += 1
                elif hunk_line_count == _MAX_HUNK_LINES:
                    condensed_lines.append("    [... diff hunk truncated ...]")
                    hunk_line_count += 1
            else:
                in_hunk = False
                condensed_lines.append(line)

        condensed_parts.append("\n".join(condensed_lines))

    result = "\n".join(condensed_parts)
    if len(result) > max_bytes:
        result = result[:max_bytes] + "\n\n[PATCH CONDENSED: remaining content omitted]"
    return result


def get_patch_history(repo_path: str, commit_offset: int) -> str:
    """
    Generate a unified patch stream for the last `commit_offset` commits using `git format-patch`.

    This uses the range:

        HEAD~commit_offset..HEAD

    which gives all commits reachable from HEAD but not from HEAD~commit_offset,
    ordered from oldest to newest, and emits them as a single mbox-style patch
    stream on stdout.
    """
    if commit_offset <= 0:
        raise ValueError("commit_offset must be a positive integer")

    repo = Path(repo_path)
    if not repo.is_dir():
        raise GitPatchError(f"Repository path does not exist or is not a directory: {repo_path}")

    # Construct the revision range, e.g. HEAD~10..HEAD
    rev_range = f"HEAD~{commit_offset}..HEAD"
    cmd = ["git", "-C", str(repo), "format-patch", "--stdout", rev_range]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore")
        raise GitPatchError(f"git format-patch failed: {stderr.strip()}") from exc

    patch_bytes = result.stdout
    if len(patch_bytes) > _MAX_PATCH_BYTES:
        patch_bytes = patch_bytes[:_MAX_PATCH_BYTES]

    return patch_bytes.decode("utf-8", errors="ignore")

