# sonar-project.properties Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `sonar-project.properties` exists in the project directory, use it as the source of truth for scanner configuration — patching the project key/name in place for temp-project runs and letting the file govern all other settings.

**Architecture:** A new `SonarPropertiesHandler` class in `sonarqube/properties_handler.py` owns both command building (minimal vs. full `-D` flags) and file patching (context manager that writes then restores). `AnalysisRunner` delegates to it. `ProjectManager.create_temp_project` gains a `command_name` parameter and generates a human-readable display name.

**Tech Stack:** Python 3.11+, `contextlib.contextmanager`, `re`, `os.environ`, `pathlib.Path`, pytest + `tmp_path` + `monkeypatch`.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/vibe_heal/sonarqube/properties_handler.py` | `SonarPropertiesHandler` class + `_patch_content` helper |
| Create | `tests/sonarqube/test_properties_handler.py` | All tests for the new module |
| Modify | `src/vibe_heal/sonarqube/analysis_runner.py` | Use handler; remove `_get_scanner_command`; add auth hint |
| Modify | `tests/sonarqube/test_analysis_runner.py` | Remove `TestGetScannerCommand`; add auth-hint tests |
| Modify | `src/vibe_heal/sonarqube/project_manager.py` | Add `command_name` param; human-readable name |
| Modify | `tests/sonarqube/test_project_manager.py` | Update name assertions; add name-format test |
| Modify | `src/vibe_heal/review/orchestrator.py` | Pass `command_name="review"` |
| Modify | `src/vibe_heal/cleanup/orchestrator.py` | Pass `command_name="cleanup"` |
| Modify | `src/vibe_heal/deduplication/orchestrator.py` | Pass `command_name="dedupe-branch"` |

---

## Task 1: `SonarPropertiesHandler` — `exists` and `build_command` (no-file path)

This task creates the file and implements the path that mirrors the current `AnalysisRunner._get_scanner_command` behaviour. The no-file path is identical to today, so existing callers regress to nothing.

**Files:**
- Create: `src/vibe_heal/sonarqube/properties_handler.py`
- Create: `tests/sonarqube/test_properties_handler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sonarqube/test_properties_handler.py`:

```python
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
        cmd = handler.build_command("test-key", "Test Project", tmp_path)
        assert "-Dsonar.projectKey=test-key" in cmd
        assert "-Dsonar.projectName=Test Project" in cmd
        assert "-Dsonar.host.url=https://sonar.test.com" in cmd
        assert "-Dsonar.token=test-token" in cmd
        assert "-Dsonar.sources=." in cmd

    def test_default_sources_dot(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", tmp_path, sources=None)
        assert "-Dsonar.sources=." in cmd

    def test_explicit_sources(self, tmp_path: Path, config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", tmp_path, sources=[Path("src/a.py"), Path("src/b.py")])
        assert "-Dsonar.sources=src/a.py,src/b.py" in cmd

    def test_basic_auth(self, tmp_path: Path, basic_auth_config: VibeHealConfig) -> None:
        handler = SonarPropertiesHandler(tmp_path, basic_auth_config)
        cmd = handler.build_command("key", "Name", tmp_path)
        assert "-Dsonar.login=user" in cmd
        assert "-Dsonar.password=pass" in cmd
        assert not any("sonar.token" in arg for arg in cmd)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/sonarqube/test_properties_handler.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — file does not exist yet.

- [ ] **Step 3: Create `properties_handler.py` with `exists` and `build_command` (no-file path)**

Create `src/vibe_heal/sonarqube/properties_handler.py`:

```python
"""sonar-project.properties detection, command building, and file patching."""

import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from vibe_heal.config import VibeHealConfig

logger = logging.getLogger(__name__)

PROPERTIES_FILENAME = "sonar-project.properties"

_KEY_RE = re.compile(r"^\s*sonar\.projectKey\s*=", re.IGNORECASE)
_NAME_RE = re.compile(r"^\s*sonar\.projectName\s*=", re.IGNORECASE)
_AUTH_PROPS_RE = re.compile(r"^\s*sonar\.(token|login|password)\s*=\s*.+", re.IGNORECASE)
_AUTH_ENV_VARS = ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN")


class SonarPropertiesHandler:
    """Detects sonar-project.properties, builds scanner commands, and patches the file for temp projects."""

    def __init__(self, project_dir: Path, config: VibeHealConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.properties_file = project_dir / PROPERTIES_FILENAME

    @property
    def exists(self) -> bool:
        return self.properties_file.exists()

    def build_command(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: list[Path] | None = None,
    ) -> list[str]:
        if not self.exists:
            return self._build_full_command(project_key, project_name, project_dir, sources)
        command = ["sonar-scanner"]
        if not self._has_auth_configured():
            if self.config.use_token_auth:
                command.append(f"-Dsonar.token={self.config.sonarqube_token}")
            else:
                command.append(f"-Dsonar.login={self.config.sonarqube_username}")
                command.append(f"-Dsonar.password={self.config.sonarqube_password}")
        return command

    def _build_full_command(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: list[Path] | None = None,
    ) -> list[str]:
        command = [
            "sonar-scanner",
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.projectName={project_name}",
            f"-Dsonar.host.url={self.config.sonarqube_url}",
        ]
        if self.config.use_token_auth:
            command.append(f"-Dsonar.token={self.config.sonarqube_token}")
        else:
            command.append(f"-Dsonar.login={self.config.sonarqube_username}")
            command.append(f"-Dsonar.password={self.config.sonarqube_password}")
        if sources:
            command.append(f"-Dsonar.sources={','.join(str(s) for s in sources)}")
        else:
            command.append("-Dsonar.sources=.")
        return command

    def _has_auth_configured(self) -> bool:
        for env_var in _AUTH_ENV_VARS:
            if os.environ.get(env_var):
                return True
        if self.exists:
            content = self.properties_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.lstrip().startswith("#"):
                    continue
                if _AUTH_PROPS_RE.match(line):
                    return True
        return False

    def _extract_property(self, content: str, key: str) -> str | None:
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*)", re.IGNORECASE)
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = pattern.match(line)
            if m:
                return m.group(1).strip()
        return None

    @contextmanager
    def patched(self, project_key: str, project_name: str) -> Generator[None, None, None]:
        if not self.exists:
            yield
            return
        original_content = self.properties_file.read_text(encoding="utf-8")
        existing_key = self._extract_property(original_content, "sonar.projectKey")
        if existing_key == project_key:
            yield
            return
        patched_content = _patch_content(original_content, project_key, project_name)
        self.properties_file.write_text(patched_content, encoding="utf-8")
        try:
            yield
        finally:
            try:
                self.properties_file.write_text(original_content, encoding="utf-8")
            except OSError:
                logger.error(
                    "Failed to restore %s. Original content:\n%s",
                    self.properties_file,
                    original_content,
                )


def _patch_content(content: str, new_key: str, new_name: str) -> str:
    lines = content.splitlines(keepends=True)
    key_idx: int | None = None
    name_idx: int | None = None
    orig_key_line: str | None = None
    orig_name_line: str | None = None

    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if _KEY_RE.match(line) and key_idx is None:
            key_idx = i
            orig_key_line = line.rstrip("\n").rstrip("\r")
        elif _NAME_RE.match(line) and name_idx is None:
            name_idx = i
            orig_name_line = line.rstrip("\n").rstrip("\r")

    recovery: list[str] = [
        "# vibe-heal: temporary analysis project. If this process was interrupted,\n",
        "# restore the lines below (remove the '#' prefix):\n",
    ]
    if orig_key_line is not None:
        recovery.append(f"# {orig_key_line.lstrip()}\n")
    if orig_name_line is not None:
        recovery.append(f"# {orig_name_line.lstrip()}\n")
    recovery.append(f"sonar.projectKey={new_key}\n")
    recovery.append(f"sonar.projectName={new_name}\n")

    present = [i for i in (key_idx, name_idx) if i is not None]
    if not present:
        return content + f"sonar.projectKey={new_key}\n" + f"sonar.projectName={new_name}\n"

    first_idx = min(present)
    skip = set(present)
    result: list[str] = []
    for i, line in enumerate(lines):
        if i == first_idx:
            result.extend(recovery)
        if i not in skip:
            result.append(line)
    return "".join(result)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/sonarqube/test_properties_handler.py::TestExists tests/sonarqube/test_properties_handler.py::TestBuildCommandNoFile -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibe_heal/sonarqube/properties_handler.py tests/sonarqube/test_properties_handler.py
git commit -m "feat: add SonarPropertiesHandler with exists and full-command build"
```

---

## Task 2: `SonarPropertiesHandler` — auth detection and minimal command (properties file path)

**Files:**
- Modify: `tests/sonarqube/test_properties_handler.py`
- (no source change needed — `_has_auth_configured` and minimal-command path are already in the file from Task 1)

- [ ] **Step 1: Add failing tests for auth detection and minimal command**

Append to `tests/sonarqube/test_properties_handler.py`:

```python
class TestHasAuthConfigured:
    def test_false_when_nothing_set(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is False

    def test_true_via_sonar_token_env(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "secret")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_sonarqube_token_env(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONARQUBE_TOKEN", "secret")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_sonar_login_env(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONAR_LOGIN", "user")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_token_in_file(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.token=file-token\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_true_via_login_in_file(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.login=user\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is True

    def test_commented_token_line_not_counted(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("# sonar.token=commented\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        assert handler._has_auth_configured() is False


class TestBuildCommandWithFile:
    def test_minimal_command_when_auth_in_file(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text(
            "sonar.projectKey=orig\nsonar.token=file-token\n"
        )
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name", tmp_path)
        assert cmd == ["sonar-scanner"]

    def test_minimal_command_when_auth_in_env(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "env-token")
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name", tmp_path)
        assert cmd == ["sonar-scanner"]

    def test_injects_token_fallback_when_no_auth(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("temp-key", "Temp Name", tmp_path)
        assert cmd == ["sonar-scanner", "-Dsonar.token=test-token"]

    def test_injects_basic_auth_fallback_when_no_auth(self, tmp_path: Path, basic_auth_config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("SONAR_TOKEN", "SONARQUBE_TOKEN", "SONAR_LOGIN"):
            monkeypatch.delenv(v, raising=False)
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, basic_auth_config)
        cmd = handler.build_command("temp-key", "Temp Name", tmp_path)
        assert cmd == ["sonar-scanner", "-Dsonar.login=user", "-Dsonar.password=pass"]

    def test_sources_not_injected_when_file_present(self, tmp_path: Path, config: VibeHealConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONAR_TOKEN", "tok")
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        handler = SonarPropertiesHandler(tmp_path, config)
        cmd = handler.build_command("key", "Name", tmp_path, sources=[Path("src/a.py")])
        assert not any("sonar.sources" in arg for arg in cmd)
```

- [ ] **Step 2: Run tests to verify they pass (implementation is already complete from Task 1)**

```bash
uv run pytest tests/sonarqube/test_properties_handler.py::TestHasAuthConfigured tests/sonarqube/test_properties_handler.py::TestBuildCommandWithFile -v
```

Expected: all 11 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/sonarqube/test_properties_handler.py
git commit -m "test: add auth detection and minimal command tests for SonarPropertiesHandler"
```

---

## Task 3: `SonarPropertiesHandler` — `_patch_content` and `patched` context manager

**Files:**
- Modify: `tests/sonarqube/test_properties_handler.py`
- (implementation already in file from Task 1)

- [ ] **Step 1: Add failing tests for `_patch_content` and `patched`**

Append to `tests/sonarqube/test_properties_handler.py`:

```python
from vibe_heal.sonarqube.properties_handler import _patch_content


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
        # No recovery block since no real key was found, just appended
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
        with pytest.raises(ValueError):
            with handler.patched("temp-key", "Temp Name"):
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
```

- [ ] **Step 2: Run tests to verify they pass (implementation already in file)**

```bash
uv run pytest tests/sonarqube/test_properties_handler.py::TestPatchContent tests/sonarqube/test_properties_handler.py::TestPatched -v
```

Expected: all 9 tests PASS.

- [ ] **Step 3: Run the full properties handler test suite**

```bash
uv run pytest tests/sonarqube/test_properties_handler.py -v
```

Expected: all 26 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/sonarqube/test_properties_handler.py
git commit -m "test: add _patch_content and patched context manager tests"
```

---

## Task 4: Update `AnalysisRunner` to use `SonarPropertiesHandler`

Replaces `_get_scanner_command` with handler delegation. Adds auth hint on failure.

**Files:**
- Modify: `src/vibe_heal/sonarqube/analysis_runner.py`
- Modify: `tests/sonarqube/test_analysis_runner.py`

- [ ] **Step 1: Update `analysis_runner.py`**

Replace the entire contents of `src/vibe_heal/sonarqube/analysis_runner.py` with:

```python
"""SonarQube analysis execution via sonar-scanner CLI."""

import asyncio
import logging
import re
import shutil
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeAPIError
from vibe_heal.sonarqube.properties_handler import SonarPropertiesHandler

console = Console()
logger = logging.getLogger(__name__)

_AUTH_ERROR_RE = re.compile(r"401|403|unauthorized|authentication", re.IGNORECASE)
_AUTH_HINT = (
    "\nHint: authentication may be configured via environment variable "
    "(SONAR_TOKEN, SONARQUBE_TOKEN) or the central scanner settings "
    "(~/.sonar/sonar-scanner.properties). Check these if you expected "
    "auth to be picked up automatically."
)


class AnalysisResult(BaseModel):
    """Result of a SonarQube analysis run."""

    success: bool
    task_id: str | None = None
    dashboard_url: str | None = None
    error_message: str | None = None


class AnalysisRunner:
    """Executes SonarQube analysis using sonar-scanner CLI.

    Runs sonar-scanner as a subprocess and waits for analysis completion
    on the SonarQube server.
    """

    def __init__(self, config: VibeHealConfig, client: SonarQubeClient) -> None:
        self.config = config
        self.client = client

    async def run_analysis(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: list[Path] | None = None,
    ) -> AnalysisResult:
        """Run SonarQube analysis on project.

        When sonar-project.properties exists in project_dir, the file governs
        all scanner configuration. The project key and name are patched in-place
        before the scanner runs and restored unconditionally afterwards.

        Args:
            project_key: SonarQube project key
            project_name: SonarQube project name
            project_dir: Root directory to analyze
            sources: Optional list of specific files/dirs (ignored when properties file present)

        Returns:
            AnalysisResult with success status and details
        """
        if not self.validate_scanner_available():
            return AnalysisResult(
                success=False,
                error_message="sonar-scanner is not installed or not in PATH. "
                "Install from: https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/",
            )

        handler = SonarPropertiesHandler(project_dir, self.config)
        command = handler.build_command(project_key, project_name, project_dir, sources)

        with handler.patched(project_key, project_name):
            try:
                console.print(f"[dim]    Executing: sonar-scanner (project: {project_key})[/dim]")
                result = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                console.print("[dim]    Waiting for scanner to complete...[/dim]")
                stdout, stderr = await result.communicate()
                console.print(f"[dim]    Scanner finished with exit code: {result.returncode}[/dim]")

                if result.returncode != 0:
                    error_output = stderr.decode() if stderr else stdout.decode()
                    console.print(f"[red]    Scanner error: {error_output[:500]}[/red]")
                    error_msg = f"sonar-scanner failed with exit code {result.returncode}: {error_output}"
                    if handler.exists and _AUTH_ERROR_RE.search(error_output):
                        error_msg += _AUTH_HINT
                    return AnalysisResult(success=False, error_message=error_msg)

                scanner_output = stdout.decode()
                console.print("[dim]    Extracting task ID from scanner output...[/dim]")
                task_id = self._extract_task_id(scanner_output)

                if not task_id:
                    console.print("[red]    Could not find task ID in scanner output[/red]")
                    console.print("[dim]    See debug log for full scanner output[/dim]")
                    logger.debug("Full scanner output when task ID extraction failed:\n%s", scanner_output)
                    return AnalysisResult(
                        success=False,
                        error_message="Could not extract task ID from scanner output",
                    )

                console.print(f"[dim]    Task ID: {task_id}[/dim]")
                console.print("[dim]    Waiting for server-side analysis to complete...[/dim]")

                try:
                    async with asyncio.timeout(300):
                        analysis_success = await self._wait_for_analysis(task_id)
                except TimeoutError:
                    console.print("[red]    Analysis timed out after 300 seconds[/red]")
                    return AnalysisResult(
                        success=False,
                        task_id=task_id,
                        error_message="Analysis timed out after 300 seconds",
                    )

                if not analysis_success:
                    console.print("[red]    Analysis failed on server[/red]")
                    return AnalysisResult(
                        success=False,
                        task_id=task_id,
                        error_message="Analysis failed on server",
                    )

                console.print("[green]    ✓ Server-side analysis completed successfully[/green]")
                dashboard_url = f"{self.config.sonarqube_url}/dashboard?id={project_key}"
                return AnalysisResult(success=True, task_id=task_id, dashboard_url=dashboard_url)

            except Exception as e:
                return AnalysisResult(success=False, error_message=f"Failed to run analysis: {e}")

    async def _wait_for_analysis(self, task_id: str) -> bool:
        """Poll SonarQube for analysis completion."""
        poll_interval = 2
        last_status = None

        while True:
            try:
                data = await self.client._request("GET", "/api/ce/task", params={"id": task_id})
                task = data.get("task", {})
                status = task.get("status")

                if status != last_status:
                    console.print(f"[dim]    Analysis status: {status}[/dim]")
                    last_status = status

                if status == "SUCCESS":
                    return True
                if status in ("FAILED", "CANCELED"):
                    console.print(f"[red]    Analysis failed with status: {status}[/red]")
                    return False

                await asyncio.sleep(poll_interval)

            except SonarQubeAPIError as e:
                console.print(f"[yellow]    Warning: API error while polling: {e}[/yellow]")
                await asyncio.sleep(poll_interval)

    def _extract_task_id(self, scanner_output: str) -> str | None:
        """Extract task ID from sonar-scanner output."""
        for line in scanner_output.split("\n"):
            if "api/ce/task?id=" in line:
                parts = line.split("api/ce/task?id=")
                if len(parts) > 1:
                    return parts[1].split()[0].strip()
        return None

    def validate_scanner_available(self) -> bool:
        """Check if sonar-scanner is installed and available."""
        return shutil.which("sonar-scanner") is not None
```

- [ ] **Step 2: Update `test_analysis_runner.py` — remove `TestGetScannerCommand`, add auth-hint tests**

Remove the entire `TestGetScannerCommand` class (lines roughly 62–113) from `tests/sonarqube/test_analysis_runner.py` and append these new tests at the end of the file:

```python
class TestAuthHint:
    @pytest.mark.asyncio
    async def test_auth_hint_added_when_properties_file_and_auth_error(
        self, analysis_runner: AnalysisRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"ERROR: 401 Unauthorized"))
        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
        ):
            result = await analysis_runner.run_analysis(
                project_key="temp-key",
                project_name="Temp",
                project_dir=tmp_path,
            )
        assert result.success is False
        assert "SONAR_TOKEN" in result.error_message

    @pytest.mark.asyncio
    async def test_no_auth_hint_without_properties_file(
        self, analysis_runner: AnalysisRunner, tmp_path: Path
    ) -> None:
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"ERROR: 401 Unauthorized"))
        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test",
                project_dir=tmp_path,
            )
        assert result.success is False
        assert "SONAR_TOKEN" not in result.error_message

    @pytest.mark.asyncio
    async def test_no_auth_hint_for_non_auth_failure(
        self, analysis_runner: AnalysisRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=orig\n")
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"ERROR: Project not found"))
        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
        ):
            result = await analysis_runner.run_analysis(
                project_key="temp-key",
                project_name="Temp",
                project_dir=tmp_path,
            )
        assert result.success is False
        assert "SONAR_TOKEN" not in result.error_message
```

- [ ] **Step 3: Run the analysis runner tests**

```bash
uv run pytest tests/sonarqube/test_analysis_runner.py -v
```

Expected: all tests PASS (the removed `TestGetScannerCommand` tests are now replaced by Task 1's `TestBuildCommandNoFile`).

- [ ] **Step 4: Run full test suite to catch regressions**

```bash
uv run pytest --tb=short -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibe_heal/sonarqube/analysis_runner.py tests/sonarqube/test_analysis_runner.py
git commit -m "feat: use SonarPropertiesHandler in AnalysisRunner, add auth hint"
```

---

## Task 5: Update `ProjectManager` with `command_name` and human-readable name

**Files:**
- Modify: `src/vibe_heal/sonarqube/project_manager.py`
- Modify: `tests/sonarqube/test_project_manager.py`

- [ ] **Step 1: Write failing tests**

In `tests/sonarqube/test_project_manager.py`, add a new test class for name format and update the `test_create_temp_project_success` assertion. Replace the `assert metadata.project_name == metadata.project_key` line with name format assertions, and add a dedicated test class:

Find the line:
```python
        assert metadata.project_name == metadata.project_key
```

Replace it with:
```python
        assert metadata.project_name == "my_project analysis user feature-new-api"
```

Then append this new test class at the end of the `TestCreateTempProject` class:

```python
    @pytest.mark.asyncio
    async def test_project_name_format_with_command(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        mock_client.create_project = AsyncMock()
        metadata = await project_manager.create_temp_project(
            base_key="my-project",
            branch_name="feature/add-login",
            user_email="alexei.eleusis@gmail.com",
            command_name="review",
        )
        assert metadata.project_name == "my-project review alexei.eleusis feature-add-login"

    @pytest.mark.asyncio
    async def test_project_name_uses_default_command_name(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        mock_client.create_project = AsyncMock()
        metadata = await project_manager.create_temp_project(
            base_key="my-project",
            branch_name="main",
            user_email="user@example.com",
        )
        assert metadata.project_name == "my-project analysis user main"

    @pytest.mark.asyncio
    async def test_project_name_email_without_at_sign(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        mock_client.create_project = AsyncMock()
        metadata = await project_manager.create_temp_project(
            base_key="proj",
            branch_name="main",
            user_email="localonly",
            command_name="cleanup",
        )
        assert metadata.project_name == "proj cleanup localonly main"

    @pytest.mark.asyncio
    async def test_project_name_branch_slashes_become_dashes(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        mock_client.create_project = AsyncMock()
        metadata = await project_manager.create_temp_project(
            base_key="proj",
            branch_name="feature/nested/branch",
            user_email="u@t.com",
            command_name="dedupe-branch",
        )
        assert metadata.project_name == "proj dedupe-branch u feature-nested-branch"
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/sonarqube/test_project_manager.py::TestCreateTempProject -v
```

Expected: `test_create_temp_project_success` FAILS (assertion mismatch on `project_name`), new tests FAIL (unexpected keyword argument `command_name`).

- [ ] **Step 3: Update `project_manager.py`**

In `src/vibe_heal/sonarqube/project_manager.py`, update `create_temp_project`:

Replace:
```python
    async def create_temp_project(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
    ) -> TempProjectMetadata:
        """Create temporary project for branch analysis.

        Project key/name format: {base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}
        Timestamp format: yymmdd-hhmm
        Sanitization: replace non-alphanumeric with underscore, lowercase.

        Args:
            base_key: Base project key (from .env.vibeheal)
            branch_name: Current branch name
            user_email: Git user email

        Returns:
            Metadata for the created project (for later cleanup)

        Raises:
            SonarQubeAPIError: If project creation fails
        """
        # Sanitize components
        sanitized_email = self._sanitize_identifier(user_email)
        sanitized_branch = self._sanitize_identifier(branch_name)

        # Generate timestamp in yymmdd-hhmm format
        timestamp = datetime.now(timezone.utc).strftime("%y%m%d-%H%M")

        # Build project key and name
        project_key = f"{base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}"
        project_name = project_key  # Use same value for both

        # Create project via API
        await self.client.create_project(project_key, project_name)

        # Build metadata
        metadata = TempProjectMetadata(
            project_key=project_key,
            project_name=project_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            base_project_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
        )

        return metadata
```

With:
```python
    async def create_temp_project(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
        command_name: str = "analysis",
    ) -> TempProjectMetadata:
        """Create temporary project for branch analysis.

        Project key format: {base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}
        Project name format: {base_key} {command_name} {email_local_part} {branch_with_dashes}
        Timestamp format: yymmdd-hhmm

        Args:
            base_key: Base project key (from .env.vibeheal)
            branch_name: Current branch name
            user_email: Git user email
            command_name: Name of the vibe-heal command (e.g. "review", "cleanup")

        Returns:
            Metadata for the created project (for later cleanup)

        Raises:
            SonarQubeAPIError: If project creation fails
        """
        sanitized_email = self._sanitize_identifier(user_email)
        sanitized_branch = self._sanitize_identifier(branch_name)
        timestamp = datetime.now(timezone.utc).strftime("%y%m%d-%H%M")
        project_key = f"{base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}"

        email_local = user_email.split("@")[0] if "@" in user_email else user_email
        branch_display = branch_name.replace("/", "-")
        project_name = f"{base_key} {command_name} {email_local} {branch_display}"

        await self.client.create_project(project_key, project_name)

        return TempProjectMetadata(
            project_key=project_key,
            project_name=project_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            base_project_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
        )
```

Also update `create_temp_project_with_settings` to accept and forward `command_name`:

Replace:
```python
    async def create_temp_project_with_settings(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
        console: Console,
    ) -> TempProjectMetadata:
        """Create temporary project and copy exclusion settings from source.

        Combines temp project creation with exclusion settings copy into a
        single operation, used by both cleanup and deduplication workflows.

        Args:
            base_key: Base project key (source project to copy settings from)
            branch_name: Current branch name
            user_email: Git user email
            console: Rich console for progress output

        Returns:
            Metadata for the created project
        """
        console.print("\n[dim]Creating temporary SonarQube project...[/dim]")
        temp_project = await self.create_temp_project(
            base_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
        )
```

With:
```python
    async def create_temp_project_with_settings(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
        console: Console,
        command_name: str = "analysis",
    ) -> TempProjectMetadata:
        """Create temporary project and copy exclusion settings from source.

        Combines temp project creation with exclusion settings copy into a
        single operation, used by both cleanup and deduplication workflows.

        Args:
            base_key: Base project key (source project to copy settings from)
            branch_name: Current branch name
            user_email: Git user email
            console: Rich console for progress output
            command_name: Name of the vibe-heal command (e.g. "cleanup", "dedupe-branch")

        Returns:
            Metadata for the created project
        """
        console.print("\n[dim]Creating temporary SonarQube project...[/dim]")
        temp_project = await self.create_temp_project(
            base_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
            command_name=command_name,
        )
```

- [ ] **Step 4: Run the project manager tests**

```bash
uv run pytest tests/sonarqube/test_project_manager.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibe_heal/sonarqube/project_manager.py tests/sonarqube/test_project_manager.py
git commit -m "feat: add command_name param and human-readable project name to create_temp_project"
```

---

## Task 6: Update orchestrators to pass `command_name`

Three orchestrators each have a `_create_temp_project` method that calls either `create_temp_project` or `create_temp_project_with_settings`.

**Files:**
- Modify: `src/vibe_heal/review/orchestrator.py`
- Modify: `src/vibe_heal/cleanup/orchestrator.py`
- Modify: `src/vibe_heal/deduplication/orchestrator.py`

- [ ] **Step 1: Update `ReviewOrchestrator._create_temp_project`**

In `src/vibe_heal/review/orchestrator.py`, find `_create_temp_project` (around line 295). Update the `create_temp_project` call:

Replace:
```python
        temp_project = await self.project_manager.create_temp_project(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
        )
```

With:
```python
        temp_project = await self.project_manager.create_temp_project(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
            command_name="review",
        )
```

- [ ] **Step 2: Update `CleanupOrchestrator._create_temp_project`**

In `src/vibe_heal/cleanup/orchestrator.py`, find `_create_temp_project` (around line 225). Update the `create_temp_project_with_settings` call:

Replace:
```python
        return await self.project_manager.create_temp_project_with_settings(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
            console=console,
        )
```

With:
```python
        return await self.project_manager.create_temp_project_with_settings(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
            console=console,
            command_name="cleanup",
        )
```

- [ ] **Step 3: Update `DedupeBranchOrchestrator._create_temp_project`**

In `src/vibe_heal/deduplication/orchestrator.py`, find `_create_temp_project` (around line 695). Update the `create_temp_project_with_settings` call:

Replace:
```python
        return await self.project_manager.create_temp_project_with_settings(
            base_key=self.config.sonarqube_project_key,
            branch_name=branch_name,
            user_email=user_email,
            console=self.console,
        )
```

With:
```python
        return await self.project_manager.create_temp_project_with_settings(
            base_key=self.config.sonarqube_project_key,
            branch_name=branch_name,
            user_email=user_email,
            console=self.console,
            command_name="dedupe-branch",
        )
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest --tb=short -q
```

Expected: all tests PASS.

- [ ] **Step 5: Run type checking**

```bash
uv run mypy
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/vibe_heal/review/orchestrator.py src/vibe_heal/cleanup/orchestrator.py src/vibe_heal/deduplication/orchestrator.py
git commit -m "feat: pass command_name to create_temp_project in all orchestrators"
```
