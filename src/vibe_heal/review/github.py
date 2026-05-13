"""GitHub Review Client for posting SonarQube reviews to GitHub PRs."""

import asyncio
import json
import re
from typing import Any, cast
from urllib.parse import urlparse

from vibe_heal.ai_tools.utils import run_command
from vibe_heal.review.models import ReviewResult


class GitHubReviewError(Exception):
    """Error during GitHub review operations."""


class NoOpenPrError(GitHubReviewError):
    """Raised when there is no open PR for the current branch."""


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
            NoOpenPrError: If no open PR exists for the current branch.
            GitHubReviewError: If auto-detection fails for other reasons.
        """
        if pr_number is not None:
            return pr_number

        result = await run_command(
            ["gh", "pr", "view", "--json", "number"],
            timeout=30,
        )
        if not result.success:
            stderr = result.stderr.strip()
            if "no pull requests found" in stderr.lower():
                raise NoOpenPrError("No open pull request found for the current branch")
            msg = f"Failed to detect PR: {stderr or 'not authenticated'}"
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
                    "--method",
                    "POST",
                    f"/repos/{owner_repo}/pulls/{pr_number}/reviews",
                    "--input",
                    "-",
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
                        "--method",
                        "POST",
                        f"/repos/{owner_repo}/pulls/{pr_number}/reviews",
                        "--input",
                        "-",
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
            ["gh", "repo", "view", "--json", "owner,name", "--jq", '"\\(.owner.login)/\\(.name)"'],
            timeout=15,
        )
        if result.success and result.stdout.strip():
            return result.stdout.strip()

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "remote",
                "get-url",
                "origin",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                remote_url = stdout.decode().strip()
                owner_repo = self._parse_remote_url(remote_url)
                if owner_repo:
                    return owner_repo
        except OSError:
            pass

        msg = "Could not detect GitHub owner/repo"
        raise GitHubReviewError(msg)

    @staticmethod
    def _parse_remote_url(remote_url: str) -> str | None:
        """Parse owner/repo from a git remote URL.

        Handles both HTTPS and SSH formats:
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git

        Args:
            remote_url: Raw remote URL string.

        Returns:
            'owner/repo' string or None if unparseable.
        """
        # SSH format: git@host:owner/repo.git
        if remote_url.startswith("git@"):
            match = re.search(r":([^/]+)/([^/.]+?)(?:\.git)?$", remote_url)
            if match:
                return f"{match.group(1)}/{match.group(2)}"
            return None

        # HTTPS format: https://host/owner/repo.git
        parsed = urlparse(remote_url)
        path = parsed.path
        # Remove leading slash and trailing .git
        path = path.strip("/").removesuffix(".git")
        parts = path.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[0]}/{parts[1]}"
        return None
