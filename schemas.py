from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PRSummarySchema(BaseModel):
    """High-level summary of the selected commits for the PR."""

    title: str = Field(
        ...,
        description="Concise, descriptive PR title suitable for a GitHub/GitLab pull request.",
    )
    summary: str = Field(
        ...,
        description="2–4 sentence high-level description of what changed and why.",
    )
    commits: List[str] = Field(
        default_factory=list,
        description="Short bullets summarizing each commit in the selected range.",
    )
    files_changed: List[str] = Field(
        default_factory=list,
        description="List of key files or directories that changed.",
    )
    change_types: List[str] = Field(
        default_factory=list,
        description=(
            "Short labels describing the nature of the changes, e.g. "
            "feature, bugfix, refactor, docs, chore, perf."
        ),
    )


class ImplicationsSchema(BaseModel):
    """Deeper analysis of impact, risks, and testing for the PR."""

    breaking_changes: List[str] = Field(
        default_factory=list,
        description="User-facing or API-breaking changes that require extra care.",
    )
    migration_notes: List[str] = Field(
        default_factory=list,
        description="Steps users or operators must take to upgrade safely (migrations, config changes, etc.).",
    )
    deps_or_config: List[str] = Field(
        default_factory=list,
        description="Notable dependency, infrastructure, or configuration changes.",
    )
    testing_notes: List[str] = Field(
        default_factory=list,
        description="How the changes were validated: tests run, environments used, manual checks.",
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        "medium",
        description="Overall qualitative risk level of this change.",
    )

