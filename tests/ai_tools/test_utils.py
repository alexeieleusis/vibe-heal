"""Tests for AI tool utilities."""

from pathlib import Path

import pytest

from vibe_heal.ai_tools.utils import build_file_prompt, write_prompt_file


class TestWritePromptFile:
    """Tests for write_prompt_file."""

    @pytest.mark.asyncio
    async def test_writes_prompt_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that the file contains the given prompt content."""
        monkeypatch.chdir(tmp_path)

        path = await write_prompt_file("do the thing")

        assert path.read_text(encoding="utf-8") == "do the thing"

    @pytest.mark.asyncio
    async def test_creates_file_in_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that the file is created in the current working directory."""
        monkeypatch.chdir(tmp_path)

        path = await write_prompt_file("prompt")

        assert path.parent == tmp_path

    @pytest.mark.asyncio
    async def test_default_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that the default suffix is .txt."""
        monkeypatch.chdir(tmp_path)

        path = await write_prompt_file("prompt")

        assert path.suffix == ".txt"

    @pytest.mark.asyncio
    async def test_custom_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a custom suffix is honored."""
        monkeypatch.chdir(tmp_path)

        path = await write_prompt_file("prompt", suffix=".md")

        assert path.suffix == ".md"


class TestBuildFilePrompt:
    """Tests for build_file_prompt."""

    def test_references_filename_and_instructs_to_follow(self) -> None:
        """Test the wrapper instruction references the file by basename."""
        result = build_file_prompt(Path("/some/dir/vibeheal_abc123.txt"))

        assert result == 'Read "vibeheal_abc123.txt" and follow the instructions in that file exactly.'
