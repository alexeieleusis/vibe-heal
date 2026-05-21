"""Tests for SonarPropertiesHandler."""

from pathlib import Path

import pytest

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.properties_handler import SonarPropertiesHandler


@pytest.fixture
def config() -> VibeHealConfig:
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_token="test-token",
        sonarqube_project_key="my-project",
    )


@pytest.fixture
def basic_auth_config() -> VibeHealConfig:
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_username="user",
        sonarqube_password="pass",
        sonarqube_project_key="my-project",
    )


class TestExists:
    def test_false_when_file_absent(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler.exists is False

    def test_true_when_file_present(self, tmp_path: Path, config: VibeHealConfig) -> None:
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=x\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler.exists is True


class TestBuildCommandNoFile:
    def test_includes_all_d_flags_token_auth(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("test-key", "Test Project")
        assert "-Dsonar.projectKey=test-key" in cmd
        assert "-Dsonar.projectName=Test Project" in cmd
        assert "-Dsonar.host.url=https://sonar.test.com" in cmd
        assert "-Dsonar.token=test-token" in cmd
        assert "-Dsonar.sources=." in cmd

    def test_default_sources_dot(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", sources=None)
        assert "-Dsonar.sources=." in cmd

    def test_explicit_sources(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", sources=[Path("src/a.py"), Path("src/b.py")])
        assert "-Dsonar.sources=src/a.py,src/b.py" in cmd

    def test_basic_auth(self, tmp_path: Path, basic_auth_config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, basic_auth_config)
        cmd = handler.build_command("key", "Name")
        assert "-Dsonar.login=user" in cmd
        assert "-Dsonar.password=pass" in cmd
        assert not any("sonar.token" in arg for arg in cmd)
