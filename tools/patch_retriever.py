from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

# Commit blocks in git format-patch start with this pattern.
_COMMIT_SEP = re.compile(r"(?=^From [0-9a-f]{40} Mon Sep 17)", re.MULTILINE)
# Start of a file diff within a commit.
_DIFF_GIT = re.compile(r"^diff --git ", re.MULTILINE)
# Extract path from first line of a diff segment "a/path b/path" (use b/ path).
_DIFF_GIT_PATH = re.compile(r"^a/.+ b/(.+)$")
# Subject line in commit header.
_SUBJECT = re.compile(r"^Subject: (.+)$", re.MULTILINE)
# Date line in commit header.
_DATE = re.compile(r"^Date: (.+)$", re.MULTILINE)


def chunk_patch(raw_patch: str) -> list[Document]:
    """Split raw git format-patch text into per-file-per-commit documents.

    Each document contains the commit subject, date, and one file's diff so that
    BM25 can retrieve by file name, function name, or other lexical content.

    Returns:
        List of Document with page_content = commit context + file diff,
        and metadata: commit_subject, file_path, commit_index.
    """
    documents: list[Document] = []
    commit_blocks = _COMMIT_SEP.split(raw_patch)

    for commit_index, block in enumerate(commit_blocks):
        block = block.strip()
        if not block:
            continue

        # Parse commit header (lines before first "diff --git").
        first_diff = _DIFF_GIT.search(block)
        if not first_diff:
            continue
        header = block[: first_diff.start()].strip()
        rest = block[first_diff.start() :].strip()

        subject_match = _SUBJECT.search(header)
        date_match = _DATE.search(header)
        commit_subject = subject_match.group(1).strip() if subject_match else ""
        # Normalize multiline subject (e.g. "Subject: [PATCH 01/27] FEATURE: ...\n context").
        commit_subject = " ".join(commit_subject.split())
        commit_date = date_match.group(1).strip() if date_match else ""

        commit_context = f"Commit: {commit_subject}\nDate: {commit_date}\n"

        # Split rest into file-diff segments (each segment starts with "diff --git").
        segments = _DIFF_GIT.split(rest)
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            # First line of segment is the "a/path b/path" part after "diff --git ".
            lines = segment.splitlines()
            if not lines:
                continue
            path_line = lines[0]
            path_match = _DIFF_GIT_PATH.match(path_line)
            file_path = path_match.group(1).strip() if path_match else path_line
            # Full diff content for this file (restore "diff --git " for readability).
            diff_content = "diff --git " + segment
            page_content = commit_context + "\n" + diff_content

            doc = Document(
                page_content=page_content,
                metadata={
                    "commit_subject": commit_subject,
                    "file_path": file_path,
                    "commit_index": commit_index,
                },
            )
            documents.append(doc)

    return documents


# Max results to retrieve; make_search_tool slices to the requested k.
_DEFAULT_K = 5
_MAX_K = 20


def build_patch_index(patch_path: str, k: int = _DEFAULT_K) -> BM25Retriever:
    """Read the raw patch from disk, chunk it, and return a BM25Retriever.

    Args:
        patch_path: Path to the patch file (e.g. patch_context.txt).
        k: Default number of results to return per search (used when building).

    Returns:
        BM25Retriever over per-file-per-commit documents.
    """
    raw = Path(patch_path).read_text(encoding="utf-8")
    docs = chunk_patch(raw)
    if not docs:
        # BM25Retriever.from_documents may not accept empty list; use a single dummy doc.
        docs = [
            Document(
                page_content="(No patch content or no file diffs found.)",
                metadata={"commit_subject": "", "file_path": "", "commit_index": 0},
            )
        ]
    return BM25Retriever.from_documents(docs, k=_MAX_K)


def make_search_tool(retriever: BM25Retriever) -> Callable[..., str]:
    """Build a search_patch(query, k) tool that uses the given BM25Retriever.

    Returns a closure suitable for use as an agent tool. The returned string
    is formatted for the agent to read (numbered chunks with metadata).
    """

    def search_patch(query: str, k: int = 5) -> str:
        """Search the git patch for specific content.

        Use this to find details about specific files, functions, variables,
        flags, error strings, or patterns mentioned in the patch.

        Args:
            query: What to search for (file name, function name, variable, flag, etc.)
            k: Number of results to return (default 5)

        Returns:
            The top matching patch chunks with commit and file context.
        """
        hits = retriever.invoke(query)
        if not hits:
            return "No matching patch chunks found."
        # Retriever returns up to _MAX_K; slice to requested k.
        hits = hits[: max(1, min(k, _MAX_K))]
        parts: list[str] = []
        for i, doc in enumerate(hits, 1):
            meta = doc.metadata or {}
            file_path = meta.get("file_path", "?")
            commit_subject = meta.get("commit_subject", "?")
            parts.append(
                f"--- Result {i} (file: {file_path}, commit: {commit_subject}) ---\n"
                f"{doc.page_content}"
            )
        return "\n\n".join(parts)

    return search_patch
