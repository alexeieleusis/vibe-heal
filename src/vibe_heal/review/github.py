"""GitHub Review Client for posting SonarQube reviews to GitHub PRs."""

import asyncio
import json
import re
import subprocess
from typing import Any, cast

from vibe_heal.ai_tools.utils import run_command
from vibe_heal.review.models import ReviewResult


class GitHubReviewError(Exception):
    """Error during GitHub review operations."""


class GitHubReviewClient:
    """Posts SonarQube review results as inline comments on GitHub PRs.

    Uses the `gh` CLI for all GitHub API interactions.
    """

    async def validate_installed(self) -> None:
        """Check that the gh CLI is installed and accessible.

        Raises:
            OSError: If gh is not installed or not in PATH.
        """
        result = await run_command(["gh", "--version"], timeout=10)
        if not result.success:
            msg = "gh CLI is not installed or not in PATH. Install it from https://cli.github.com/"
            raise OSError(msg)

    async def detect_pr(self, pr_number: int | None = None) -> int:
        """Get the PR number for review posting.

        Args:
            pr_number: Explicit PR number. If provided, returned directly.

        Returns:
            The PR number.

        Raises:
            GitHubReviewError: If auto-detection fails (e.g., not authenticated).
        """
        if pr_number is not None:
            return pr_number

        result = await run_command(
            ["gh", "pr", "view", "--json", "number"],
            timeout=30,
        )
        if not result.success:
            msg = f"Failed to detect PR: {result.stderr.strip() or 'not authenticated'}"
            raise GitHubReviewError(msg)

        data: dict[str, object] = json.loads(result.stdout)
        return cast(int, data["number"])

    async def post_review(self, pr_number: int, report: ReviewResult) -> None:
        """Post a review with inline comments on a GitHub PR.

        Builds a single GitHub review payload with per-file inline comments.
        If the inline review fails (e.g., lines outside the diff), falls back
        to posting a top-level comment with all issues.

        Args:
            pr_number: The PR number to post the review on.
            report: The SonarQube review result containing issues.

        Raises:
            GitHubReviewError: If both the inline review and fallback fail.
        """
        owner_repo = await self._get_owner_repo()
        payload = self._build_payload(report)

        try:
            await self._post_json(
                [
                    "gh",
                    "api",
                    "POST",
                    f"/repos/{owner_repo}/pulls/{pr_number}/reviews",
                ],
                payload,
            )
        except GitHubReviewError:
            fallback = self._build_fallback_payload(report)
            try:
                await self._post_json(
                    [
                        "gh",
                        "api",
                        "POST",
                        f"/repos/{owner_repo}/pulls/{pr_number}/reviews",
                    ],
                    fallback,
                )
            except GitHubReviewError as e:
                raise GitHubReviewError(f"Review posting failed: {e}") from e

    def _build_payload(self, report: ReviewResult) -> dict[str, Any]:
        """Build the GitHub review payload with inline comments."""
        comments: list[dict[str, Any]] = []
        for file_review in report.files:
            for issue in file_review.issues:
                body = f"**{issue.rule}** {issue.message}"
                if issue.doc_url:
                    body += f"\n\n{issue.doc_url}"
                comments.append({
                    "path": file_review.file_path,
                    "line": issue.line,
                    "body": body,
                })
        return {
            "event": "COMMENT",
            "comments": comments,
        }

    def _build_fallback_payload(self, report: ReviewResult) -> dict[str, Any]:
        """Build a fallback payload with a top-level summary comment."""
        lines: list[str] = []
        for file_review in report.files:
            for issue in file_review.issues:
                lines.append(
                    f"- **{issue.rule}** ({file_review.file_path}:{issue.line}) {issue.message}",
                )
        return {
            "event": "COMMENT",
            "body": "\n".join(lines),
            "comments": [],
        }

    async def _post_json(self, cmd: list[str], payload: dict[str, Any]) -> None:
        """Post JSON data to a gh API endpoint via stdin."""
        stdin_data = json.dumps(payload).encode()
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate(stdin_data)
        if process.returncode != 0:
            error_msg = stderr.decode().strip() or "Unknown error"
            raise GitHubReviewError(error_msg)

    async def _get_owner_repo(self) -> str:
        """Detect the GitHub owner/repo from the current repository.

        Tries gh CLI first, falls back to parsing the git remote URL.

        Returns:
            String in 'owner/repo' format.
        """
        result = await run_command(
            ["gh", "repo", "view", "--json", "owner,name", "--jq", '"\\(.owner)/\\(.name)"'],
            timeout=15,
        )
        if result.success and result.stdout.strip():
            return result.stdout.strip()

        try:
            remote_url = (
                subprocess
                .check_output(
                    ["git", "remote", "get-url", "origin"],  # noqa: S607
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            match = re.search(r"[:/]([^/]+)/([^/.]+)", remote_url)
            if match:
                return f"{match.group(1)}/{match.group(2)}"
        except subprocess.CalledProcessError:
            pass

        msg = "Could not detect GitHub owner/repo"
        raise GitHubReviewError(msg)
