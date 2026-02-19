from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final


_MAX_PATCH_BYTES: Final[int] = 500_000  # ~500KB cap; Gemini 1M context can handle more


class GitPatchError(RuntimeError):
    """Raised when we cannot generate a patch from the target repository."""


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

