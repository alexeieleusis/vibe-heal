"""Resolves a human-readable label identifying which SonarQube project a review run covers.

Some repos run `vibe-heal review` from several subdirectories in the same PR (each with
its own sonar-project.properties / SonarQube project). Without a label, the PR comments
those runs post are indistinguishable from one another.
"""

from pathlib import Path

from git import Repo
from git.exc import InvalidGitRepositoryError

from vibe_heal.sonarqube.properties_handler import PROPERTIES_FILENAME, extract_property


def resolve_project_label(project_dir: Path, repo: Repo | None = None) -> str:
    """Resolve a label identifying the SonarQube project analyzed from project_dir.

    Priority order:
    1. `sonar.projectName` (or `sonar.projectKey`) from project_dir's sonar-project.properties.
    2. project_dir's path relative to the git repository root (or the repo root's own
       directory name, when project_dir IS the repo root).
    3. project_dir's own directory name, when it is not inside a git repository at all.

    Args:
        project_dir: Directory the review is running against.
        repo: Optional already-resolved `Repo` for project_dir's repository (e.g. from an
            existing `BranchAnalyzer`), reused instead of re-walking the filesystem to find `.git`.
    """
    properties_file = project_dir / PROPERTIES_FILENAME
    if properties_file.is_file():
        content = properties_file.read_text(encoding="utf-8")
        label = extract_property(content, "sonar.projectName") or extract_property(content, "sonar.projectKey")
        if label:
            return label

    resolved_dir = project_dir.resolve()
    try:
        if repo is None:
            repo = Repo(project_dir, search_parent_directories=True)
        repo_root = Path(repo.working_dir).resolve()
        relative = resolved_dir.relative_to(repo_root)
    except (InvalidGitRepositoryError, ValueError):
        return resolved_dir.name
    return relative.as_posix() if relative != Path(".") else repo_root.name
