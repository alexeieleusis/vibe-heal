"""Tests for resolve_project_label."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from git import Repo
from git.exc import InvalidGitRepositoryError

from vibe_heal.review.project_label import resolve_project_label


def _mock_repo(working_dir: Path) -> MagicMock:
    repo = MagicMock(spec=Repo)
    repo.working_dir = str(working_dir)
    return repo


class TestResolveProjectLabel:
    """Tests for resolve_project_label."""

    def test_uses_sonar_project_name_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "sonar-project.properties").write_text(
            "sonar.projectKey=my-key\nsonar.projectName=My Nice Project\n"
        )
        assert resolve_project_label(tmp_path) == "My Nice Project"

    def test_falls_back_to_sonar_project_key_when_no_name(self, tmp_path: Path) -> None:
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=my-key\n")
        assert resolve_project_label(tmp_path) == "my-key"

    def test_ignores_commented_properties(self, tmp_path: Path) -> None:
        (tmp_path / "sonar-project.properties").write_text("#sonar.projectName=Commented\nsonar.projectKey=my-key\n")
        assert resolve_project_label(tmp_path) == "my-key"

    def test_uses_repo_relative_path_when_no_properties_file(self, tmp_path: Path) -> None:
        repo_root = tmp_path
        subdir = repo_root / "services" / "api"
        subdir.mkdir(parents=True)
        with patch("vibe_heal.review.project_label.Repo", return_value=_mock_repo(repo_root)):
            assert resolve_project_label(subdir) == "services/api"

    def test_uses_repo_root_name_when_project_dir_is_repo_root(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()
        with patch("vibe_heal.review.project_label.Repo", return_value=_mock_repo(repo_root)):
            assert resolve_project_label(repo_root) == "my-repo"

    def test_uses_directory_name_when_not_in_git_repo(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "standalone-dir"
        project_dir.mkdir()
        with patch(
            "vibe_heal.review.project_label.Repo",
            side_effect=InvalidGitRepositoryError("not a repo"),
        ):
            assert resolve_project_label(project_dir) == "standalone-dir"

    def test_properties_file_takes_priority_over_git_path(self, tmp_path: Path) -> None:
        repo_root = tmp_path
        subdir = repo_root / "services" / "api"
        subdir.mkdir(parents=True)
        (subdir / "sonar-project.properties").write_text("sonar.projectName=Api Service\n")
        with patch("vibe_heal.review.project_label.Repo", return_value=_mock_repo(repo_root)):
            assert resolve_project_label(subdir) == "Api Service"

    def test_uses_directory_name_when_project_dir_not_under_reported_repo_root(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "unrelated-dir"
        project_dir.mkdir()
        unrelated_repo_root = tmp_path / "some-other-repo"
        unrelated_repo_root.mkdir()
        with patch("vibe_heal.review.project_label.Repo", return_value=_mock_repo(unrelated_repo_root)):
            assert resolve_project_label(project_dir) == "unrelated-dir"

    def test_reuses_passed_in_repo_instead_of_constructing_new_one(self, tmp_path: Path) -> None:
        repo_root = tmp_path
        subdir = repo_root / "services" / "api"
        subdir.mkdir(parents=True)
        with patch("vibe_heal.review.project_label.Repo", side_effect=AssertionError("should not construct a Repo")):
            assert resolve_project_label(subdir, repo=_mock_repo(repo_root)) == "services/api"
