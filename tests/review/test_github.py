"""Tests for GitHubReviewClient."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from vibe_heal.review.github import GitHubReviewClient, GitHubReviewError
from vibe_heal.review.models import FileReview, ReviewIssue, ReviewResult


@pytest.fixture
def sample_report() -> ReviewResult:
    """Create a sample ReviewResult for testing."""
    return ReviewResult(
        project_key="test-project",
        branch="feature/test",
        base_branch="origin/main",
        files=[
            FileReview(
                file_path="src/example.py",
                issues=[
                    ReviewIssue(
                        rule="python:S1481",
                        message="Remove unused variable",
                        line=10,
                        severity="MAJOR",
                        doc_url="https://rules.example.com/S1481",
                    ),
                    ReviewIssue(
                        rule="python:S1192",
                        message="Useless import",
                        line=25,
                        severity="MINOR",
                    ),
                ],
            ),
        ],
    )


class TestValidateInstalled:
    """Tests for validate_installed."""

    @pytest.mark.asyncio
    async def test_raises_when_gh_not_installed(self, mocker) -> None:
        """validate_installed raises OSError when gh is not installed."""
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=False),
        )

        client = GitHubReviewClient()
        with pytest.raises(OSError, match="gh CLI"):
            await client.validate_installed()


class TestDetectPr:
    """Tests for detect_pr."""

    @pytest.mark.asyncio
    async def test_uses_explicit_number(self) -> None:
        """detect_pr returns the explicit PR number when provided."""
        client = GitHubReviewClient()
        result = await client.detect_pr(pr_number=42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_auto_detects_from_current_branch(self, sample_report, mocker) -> None:
        """detect_pr auto-detects PR number from gh pr view."""
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(
                success=True,
                stdout='{"number": 73}',
            ),
        )

        client = GitHubReviewClient()
        pr_number = await client.detect_pr()
        assert pr_number == 73

    @pytest.mark.asyncio
    async def test_raises_when_not_authenticated(self, mocker) -> None:
        """detect_pr raises GitHubReviewError when gh is not authenticated."""
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(
                success=False,
                stderr="error: you are not authenticated",
            ),
        )

        client = GitHubReviewClient()
        with pytest.raises(GitHubReviewError, match="authenticated"):
            await client.detect_pr()


class TestPostReview:
    """Tests for post_review."""

    @pytest.mark.asyncio
    async def test_single_api_call(self, sample_report, mocker) -> None:
        """post_review makes a single gh api POST call."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b'{"id": 123}', b"")
        mock_process.returncode = 0
        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(42, sample_report)

        assert mock_process.communicate.call_count == 1
        call_args = mock_process.communicate.call_args
        stdin_json = json.loads(call_args[0][0])
        assert stdin_json["event"] == "COMMENT"
        assert len(stdin_json["comments"]) == 2

    @pytest.mark.asyncio
    async def test_inline_comment_format(self, sample_report, mocker) -> None:
        """Inline comment body contains rule, message, and doc_url."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"{}", b"")
        mock_process.returncode = 0
        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(42, sample_report)

        stdin_json = json.loads(mock_process.communicate.call_args[0][0])
        comment_with_url = stdin_json["comments"][0]
        assert comment_with_url["body"] == (
            "**python:S1481** Remove unused variable\n\nhttps://rules.example.com/S1481"
        )
        assert comment_with_url["path"] == "src/example.py"
        assert comment_with_url["line"] == 10

        comment_no_url = stdin_json["comments"][1]
        assert comment_no_url["body"] == "**python:S1192** Useless import"

    @pytest.mark.asyncio
    async def test_fallback_comment_for_rejected_lines(self, sample_report, mocker) -> None:
        """When inline review fails, post_review posts a top-level fallback comment."""
        mock_fail = AsyncMock()
        mock_fail.communicate.return_value = (
            b'{"message": "Unprocessable Entity"}',
            b"",
        )
        mock_fail.returncode = 1

        mock_success = AsyncMock()
        mock_success.communicate.return_value = (b"{}", b"")
        mock_success.returncode = 0

        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            side_effect=[mock_fail, mock_success],
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(42, sample_report)

        assert mock_fail.communicate.call_count == 1
        assert mock_success.communicate.call_count == 1
        fallback_json = json.loads(mock_success.communicate.call_args[0][0])
        assert fallback_json["event"] == "COMMENT"
        assert fallback_json["comments"] == []
        assert "python:S1481" in fallback_json["body"]
        assert "python:S1192" in fallback_json["body"]

    @pytest.mark.asyncio
    async def test_builds_correct_api_endpoint(self, sample_report, mocker) -> None:
        """post_review calls gh api with the correct repository endpoint."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"{}", b"")
        mock_process.returncode = 0

        mock_create = mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )

        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(
                success=False,
            ),
        )
        with patch(
            "vibe_heal.review.github.subprocess.check_output",
            return_value=b"git@github.com:myorg/myrepo.git\n",
        ):
            client = GitHubReviewClient()
            await client.post_review(42, sample_report)

        args, _ = mock_create.call_args
        assert args[0] == "gh"
        assert "api" in args
        assert "POST" in args
        assert any("repos/myorg/myrepo/pulls/42/reviews" in str(a) for a in args)

    @pytest.mark.asyncio
    async def test_uses_gh_repo_for_owner_repo(self, sample_report, mocker) -> None:
        """post_review prefers gh CLI for owner/repo detection."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"{}", b"")
        mock_process.returncode = 0
        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )

        mock_run = mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="ghorg/ghrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(99, sample_report)

        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gh"

    @pytest.mark.asyncio
    async def test_raises_when_fallback_also_fails(self, sample_report, mocker) -> None:
        """post_review raises GitHubReviewError when both attempts fail."""
        mock_fail = AsyncMock()
        mock_fail.communicate.return_value = (
            b'{"message": "Server error"}',
            b"internal error",
        )
        mock_fail.returncode = 1

        mock_fail2 = AsyncMock()
        mock_fail2.communicate.return_value = (
            b'{"message": "Server error"}',
            b"internal error",
        )
        mock_fail2.returncode = 1

        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            side_effect=[mock_fail, mock_fail2],
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        with pytest.raises(GitHubReviewError, match="failed"):
            await client.post_review(42, sample_report)

    @pytest.mark.asyncio
    async def test_empty_report_posts_empty_review(self, mocker) -> None:
        """post_review handles a report with no issues gracefully."""
        empty_report = ReviewResult(
            project_key="test",
            branch="main",
            base_branch="origin/main",
            files=[],
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"{}", b"")
        mock_process.returncode = 0
        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(1, empty_report)

        stdin_json = json.loads(mock_process.communicate.call_args[0][0])
        assert stdin_json["event"] == "COMMENT"
        assert stdin_json["comments"] == []

    @pytest.mark.asyncio
    async def test_multiple_files_aggregated(self, mocker) -> None:
        """post_review aggregates comments from multiple files into one review."""
        multi_file_report = ReviewResult(
            project_key="test",
            branch="feat",
            base_branch="origin/main",
            files=[
                FileReview(
                    file_path="src/a.py",
                    issues=[ReviewIssue(rule="python:S1", message="Issue A1", line=1)],
                ),
                FileReview(
                    file_path="src/b.py",
                    issues=[
                        ReviewIssue(rule="python:S2", message="Issue B1", line=10),
                        ReviewIssue(rule="python:S3", message="Issue B2", line=20),
                    ],
                ),
            ],
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"{}", b"")
        mock_process.returncode = 0
        mocker.patch(
            "vibe_heal.review.github.asyncio.create_subprocess_exec",
            return_value=mock_process,
        )
        mocker.patch(
            "vibe_heal.review.github.run_command",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(success=True, stdout="myorg/myrepo"),
        )

        client = GitHubReviewClient()
        await client.post_review(5, multi_file_report)

        stdin_json = json.loads(mock_process.communicate.call_args[0][0])
        assert len(stdin_json["comments"]) == 3
        paths = {c["path"] for c in stdin_json["comments"]}
        assert "src/a.py" in paths
        assert "src/b.py" in paths
