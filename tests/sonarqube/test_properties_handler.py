"""Tests for SonarPropertiesHandler."""

from pathlib import Path

import pytest

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.properties_handler import SonarPropertiesHandler, _patch_content


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


class TestHasAuthConfigured:
    def test_false_when_nothing_set(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is False

    def test_true_via_sonar_token_env(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "secret")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_sonarqube_token_env(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SONARQUBE_TOKEN", "secret")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_sonar_login_env(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SONAR_LOGIN", "user")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_token_in_file(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.token=file-token\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_login_in_file(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.login=user\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_commented_token_line_not_counted(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("# sonar.token=commented\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is False


class TestBuildCommandWithFile:
    def test_minimal_command_when_auth_in_file(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\nsonar.token=file-token\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name")
        assert cmd == ["sonar-scanner"]

    def test_minimal_command_when_auth_in_env(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "env-token")
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name")
        assert cmd == ["sonar-scanner"]

    def test_injects_token_fallback_when_no_auth(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name")
        assert cmd == ["sonar-scanner", "-Dsonar.token=test-token"]

    def test_injects_basic_auth_fallback_when_no_auth(
        self, tmp_path: Path, basic_auth_config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, basic_auth_config)
        cmd = handler.build_command("temp-key", "Temp Name")
        assert cmd == ["sonar-scanner", "-Dsonar.login=user", "-Dsonar.password=pass"]

    def test_sources_not_injected_when_file_present(
        self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "tok")
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", sources=[Path("src/a.py")])
        assert not any("sonar.sources" in arg for arg in cmd)


class TestPatchContent:
    def test_replaces_key_and_name_with_recovery_block(self) -> None:
        original = "sonar.projectKey=my-project\nsonar.projectName=My Project\nsonar.sources=.\n"
        result = _patch_content(original, "temp-key-123", "my-project review user main")
        assert "sonar.projectKey=temp-key-123" in result
        assert "sonar.projectName=my-project review user main" in result
        assert "# sonar.projectKey=my-project" in result
        assert "# sonar.projectName=My Project" in result
        assert "vibe-heal: temporary analysis project" in result
        assert "sonar.sources=." in result  # unrelated line preserved

    def test_key_only_in_file_appends_new_name(self) -> None:
        original = "sonar.projectKey=my-project\nsonar.sources=.\n"
        result = _patch_content(original, "temp-key-123", "my-project review user main")
        assert "sonar.projectKey=temp-key-123" in result
        assert "sonar.projectName=my-project review user main" in result
        assert "# sonar.projectKey=my-project" in result
        assert "sonar.sources=." in result

    def test_neither_key_nor_name_appended_at_end(self) -> None:
        original = "sonar.sources=.\nsonar.host.url=https://sonar.test.com\n"
        result = _patch_content(original, "temp-key-123", "my-project review user main")
        assert result.endswith("sonar.projectKey=temp-key-123\nsonar.projectName=my-project review user main\n")
        assert "sonar.sources=." in result

    def test_commented_key_line_not_treated_as_property(self) -> None:
        original = "# sonar.projectKey=commented\nsonar.sources=.\n"
        result = _patch_content(original, "temp-key-123", "my-project review user main")
        # No real key found, so values appended at end
        assert result.endswith("sonar.projectKey=temp-key-123\nsonar.projectName=my-project review user main\n")


class TestPatched:
    def test_patches_file_during_with_block(self, tmp_path: Path, config: VibeHealConfig) -> None:
        props = tmp_path / "sonar-project.properties"
        props.write_text("sonar.projectKey=original\nsonar.sources=.\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        with handler.patched("temp-key", "Temp Name"):
            content = props.read_text()
            assert "sonar.projectKey=temp-key" in content
            assert "# sonar.projectKey=original" in content

    def test_restores_file_after_normal_exit(self, tmp_path: Path, config: VibeHealConfig) -> None:
        original = "sonar.projectKey=original\nsonar.sources=.\n"
        props = tmp_path / "sonar-project.properties"
        props.write_text(original)
        handler = SonarPropertiesHandler(tmp_path, config)
        with handler.patched("temp-key", "Temp Name"):
            pass
        assert props.read_text() == original

    def test_restores_file_after_exception(self, tmp_path: Path, config: VibeHealConfig) -> None:
        original = "sonar.projectKey=original\nsonar.sources=.\n"
        props = tmp_path / "sonar-project.properties"
        props.write_text(original)
        handler = SonarPropertiesHandler(tmp_path, config)
        with pytest.raises(ValueError), handler.patched("temp-key", "Temp Name"):
            raise ValueError("simulated failure")
        assert props.read_text() == original

    def test_noop_when_file_absent(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        with handler.patched("temp-key", "Temp Name"):
            pass  # must not raise

    def test_noop_when_key_already_matches(self, tmp_path: Path, config: VibeHealConfig) -> None:
        original = "sonar.projectKey=same-key\n"
        props = tmp_path / "sonar-project.properties"
        props.write_text(original)
        handler = SonarPropertiesHandler(tmp_path, config)
        with handler.patched("same-key", "Same Name"):
            assert props.read_text() == original  # file untouched
