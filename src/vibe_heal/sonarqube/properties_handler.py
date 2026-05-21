"""sonar-project.properties detection, command building, and file patching."""

import logging
import os
import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

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
        sources: list[Path] | None = None,
    ) -> list[str]:
        if not self.exists:
            return self._build_full_command(project_key, project_name, sources)
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
                logger.exception(
                    "Failed to restore %s. Original content:\n%s",
                    self.properties_file,
                    original_content,
                )


def _find_key_name_indices(
    lines: list[str],
) -> tuple[int | None, int | None, str | None, str | None]:
    """Return (key_idx, name_idx, orig_key_line, orig_name_line) from a properties file."""
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
    return key_idx, name_idx, orig_key_line, orig_name_line


def _build_recovery_block(
    orig_key_line: str | None, orig_name_line: str | None, new_key: str, new_name: str
) -> list[str]:
    """Build the recovery comment block and new key/name lines."""
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
    return recovery


def _patch_content(content: str, new_key: str, new_name: str) -> str:
    lines = content.splitlines(keepends=True)
    key_idx, name_idx, orig_key_line, orig_name_line = _find_key_name_indices(lines)

    recovery = _build_recovery_block(orig_key_line, orig_name_line, new_key, new_name)

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
