"""Tests for VCS factory and auto-detection."""

import shutil
from pathlib import Path

import git
import hglib  # type: ignore[import-untyped]
import pytest

from vibe_heal.vcs.factory import VCSFactory, VCSType
from vibe_heal.vcs.git.branch_analyzer import GitBranchAnalyzer
from vibe_heal.vcs.git.manager import GitManager
from vibe_heal.vcs.mercurial.branch_analyzer import MercurialBranchAnalyzer
from vibe_heal.vcs.mercurial.manager import MercurialManager

# Helper to check if Mercurial is installed
MERCURIAL_AVAILABLE = shutil.which("hg") is not None
requires_mercurial = pytest.mark.skipif(
    not MERCURIAL_AVAILABLE,
    reason="Mercurial (hg) is not installed",
)


class TestVCSDetection:
    """Tests for VCS detection."""

    def test_detect_git_repo(self, tmp_path: Path) -> None:
        """Test detection of Git repository."""
        git.Repo.init(tmp_path)

        vcs_type = VCSFactory.detect_vcs(tmp_path)

        assert vcs_type == VCSType.GIT

    @requires_mercurial
    def test_detect_mercurial_repo(self, tmp_path: Path) -> None:
        """Test detection of Mercurial repository."""
        hglib.init(str(tmp_path))

        vcs_type = VCSFactory.detect_vcs(tmp_path)

        assert vcs_type == VCSType.MERCURIAL

    @requires_mercurial
    def test_git_takes_precedence_when_both_exist(self, tmp_path: Path) -> None:
        """Test that Git is detected first if both .git and .hg exist."""
        git.Repo.init(tmp_path)
        hglib.init(str(tmp_path))

        vcs_type = VCSFactory.detect_vcs(tmp_path)

        assert vcs_type == VCSType.GIT

    def test_defaults_to_git_when_neither_exists(self, tmp_path: Path) -> None:
        """Test that Git is default when no VCS is detected."""
        vcs_type = VCSFactory.detect_vcs(tmp_path)

        assert vcs_type == VCSType.GIT

    def test_detect_searches_parent_directories(self, tmp_path: Path) -> None:
        """Test that detection searches parent directories."""
        # Create git repo in parent
        git.Repo.init(tmp_path)

        # Check from child directory
        child_dir = tmp_path / "subdir" / "nested"
        child_dir.mkdir(parents=True)

        vcs_type = VCSFactory.detect_vcs(child_dir)

        assert vcs_type == VCSType.GIT

    def test_detect_from_current_directory(self) -> None:
        """Test detection from current directory (no path specified)."""
        # Should detect Git since the project itself is a Git repo
        vcs_type = VCSFactory.detect_vcs()

        assert vcs_type == VCSType.GIT


class TestVCSFactoryCreateManager:
    """Tests for VCS manager factory."""

    def test_create_git_manager_explicit(self, tmp_path: Path) -> None:
        """Test creating GitManager with explicit type."""
        git.Repo.init(tmp_path)

        manager = VCSFactory.create_manager(tmp_path, vcs_type=VCSType.GIT)

        assert isinstance(manager, GitManager)
        assert manager.is_repository()

    @requires_mercurial
    def test_create_mercurial_manager_explicit(self, tmp_path: Path) -> None:
        """Test creating MercurialManager with explicit type."""
        hglib.init(str(tmp_path))

        manager = VCSFactory.create_manager(tmp_path, vcs_type=VCSType.MERCURIAL)

        assert isinstance(manager, MercurialManager)
        assert manager.is_repository()

    def test_create_manager_auto_detect_git(self, tmp_path: Path) -> None:
        """Test auto-detection creates GitManager."""
        git.Repo.init(tmp_path)

        manager = VCSFactory.create_manager(tmp_path)

        assert isinstance(manager, GitManager)

    @requires_mercurial
    def test_create_manager_auto_detect_mercurial(self, tmp_path: Path) -> None:
        """Test auto-detection creates MercurialManager."""
        hglib.init(str(tmp_path))

        manager = VCSFactory.create_manager(tmp_path)

        assert isinstance(manager, MercurialManager)

    def test_create_manager_unsupported_type(self, tmp_path: Path) -> None:
        """Test that unsupported VCS type raises ValueError."""
        # Create a fake VCS type
        fake_vcs_type = "svn"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unsupported VCS type"):
            VCSFactory.create_manager(tmp_path, vcs_type=fake_vcs_type)


class TestVCSFactoryCreateBranchAnalyzer:
    """Tests for branch analyzer factory."""

    def test_create_git_branch_analyzer_explicit(self, tmp_path: Path) -> None:
        """Test creating GitBranchAnalyzer with explicit type."""
        git.Repo.init(tmp_path)

        analyzer = VCSFactory.create_branch_analyzer(tmp_path, vcs_type=VCSType.GIT)

        assert isinstance(analyzer, GitBranchAnalyzer)

    @requires_mercurial
    def test_create_mercurial_branch_analyzer_explicit(self, tmp_path: Path) -> None:
        """Test creating MercurialBranchAnalyzer with explicit type."""
        hglib.init(str(tmp_path))

        analyzer = VCSFactory.create_branch_analyzer(tmp_path, vcs_type=VCSType.MERCURIAL)

        assert isinstance(analyzer, MercurialBranchAnalyzer)

    def test_create_analyzer_auto_detect_git(self, tmp_path: Path) -> None:
        """Test auto-detection creates GitBranchAnalyzer."""
        git.Repo.init(tmp_path)

        analyzer = VCSFactory.create_branch_analyzer(tmp_path)

        assert isinstance(analyzer, GitBranchAnalyzer)

    @requires_mercurial
    def test_create_analyzer_auto_detect_mercurial(self, tmp_path: Path) -> None:
        """Test auto-detection creates MercurialBranchAnalyzer."""
        hglib.init(str(tmp_path))

        analyzer = VCSFactory.create_branch_analyzer(tmp_path)

        assert isinstance(analyzer, MercurialBranchAnalyzer)

    def test_create_analyzer_unsupported_type(self, tmp_path: Path) -> None:
        """Test that unsupported VCS type raises ValueError."""
        fake_vcs_type = "svn"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unsupported VCS type"):
            VCSFactory.create_branch_analyzer(tmp_path, vcs_type=fake_vcs_type)


class TestVCSTypeEnum:
    """Tests for VCSType enum."""

    def test_vcs_type_values(self) -> None:
        """Test VCSType enum values."""
        assert VCSType.GIT.value == "git"
        assert VCSType.MERCURIAL.value == "mercurial"

    def test_vcs_type_display_names(self) -> None:
        """Test VCSType display names."""
        assert VCSType.GIT.display_name == "Git"
        assert VCSType.MERCURIAL.display_name == "Mercurial"
