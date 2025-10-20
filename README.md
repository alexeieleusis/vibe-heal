# vibe-heal

[![Release](https://img.shields.io/github/v/release/alexeieleusis/vibe-heal)](https://img.shields.io/github/v/release/alexeieleusis/vibe-heal)
[![Build status](https://img.shields.io/github/actions/workflow/status/alexeieleusis/vibe-heal/main.yml?branch=main)](https://github.com/alexeieleusis/vibe-heal/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/alexeieleusis/vibe-heal/branch/main/graph/badge.svg)](https://codecov.io/gh/alexeieleusis/vibe-heal)
[![Commit activity](https://img.shields.io/github/commit-activity/m/alexeieleusis/vibe-heal)](https://img.shields.io/github/commit-activity/m/alexeieleusis/vibe-heal)
[![License](https://img.shields.io/github/license/alexeieleusis/vibe-heal)](https://img.shields.io/github/license/alexeieleusis/vibe-heal)

AI-powered SonarQube issue remediation that automatically fixes your code quality problems using Claude Code or Aider.

- **Github repository**: <https://github.com/alexeieleusis/vibe-heal/>
- **Documentation**: <https://alexeieleusis.github.io/vibe-heal/>

## Overview

vibe-heal integrates with SonarQube to automatically fix code quality issues using AI coding assistants. It:

- Fetches issues from your SonarQube server
- Processes issues in reverse line order (to avoid line number shifts)
- Invokes AI tools (Claude Code or Aider) to fix each issue
- Creates a git commit for each successful fix
- Provides detailed progress reporting

## Current Status: ✅ Core Features Complete

**Completed Phases**:
- ✅ Phase 0: Project Setup
- ✅ Phase 1: Configuration Management
- ✅ Phase 2: SonarQube API Integration
- ✅ Phase 3: Issue Processing Engine
- ✅ Phase 4: AI Tool Integration (Claude Code)
- ✅ Phase 5: Git Integration & Auto-Commit
- ✅ Phase 6: CLI & Orchestration
- ✅ Phase 8: Aider Integration

**Overall Progress**: 157 tests passing, 82% code coverage

**Status**: The core workflow is complete and working end-to-end! You can now use vibe-heal to automatically fix SonarQube issues with **Claude Code** or **Aider**.

**Next Steps**: Phase 7 (Safety Features), Additional enhancements

See [ROADMAP.md](docs/ROADMAP.md) for detailed development plan.

## Features

- ✅ Fetch SonarQube issues for any file
- ✅ AI-powered issue fixing with **Claude Code** or **Aider**
- ✅ **Enriched AI prompts** with full rule documentation and code context
- ✅ Automatic git commits per fix with conventional commit format
- ✅ **Enhanced commit messages** with rule links and detailed context
- ✅ Smart issue ordering (reverse line order to avoid line number shifts)
- ✅ Safe operation (checks for uncommitted changes in target file)
- ✅ Detailed progress indicators and summary reports
- ✅ Support for both SonarQube old and new API formats
- ✅ Dry-run mode for testing without committing
- ✅ Configurable severity filtering and issue limits
- ✅ AI tool auto-detection (tries Claude Code first, then Aider)
- ✅ Aider integration with Ollama/OpenAI/Anthropic support
- 🔜 Additional safety features (Phase 7)

## Quick Start

### 1. Install vibe-heal

```bash
# Clone the repository
git clone https://github.com/alexeieleusis/vibe-heal.git
cd vibe-heal

# Install with uv
uv pip install -e .
```

### 2. Install an AI Tool

**Option A: Claude Code**
```bash
# Install Claude Code CLI (if not already installed)
# See https://docs.claude.com/claude-code for installation instructions
```

**Option B: Aider**
```bash
# Install Aider
pip install aider-chat

# If using Ollama, make sure it's running
# Download and start Ollama from https://ollama.ai
ollama pull gemma3:27b  # or your preferred model
```

### 3. Configure SonarQube connection

**For Claude Code** (auto-detected):
```bash
cat > .env.vibeheal <<EOF
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token_here
SONARQUBE_PROJECT_KEY=your_project_key
EOF
```

**For Aider with Ollama**:
```bash
cat > .env.vibeheal <<EOF
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token_here
SONARQUBE_PROJECT_KEY=your_project_key

AI_TOOL=aider
AIDER_MODEL=ollama_chat/gemma3:27b
AIDER_API_BASE=http://127.0.0.1:11434
EOF
```

### 4. Fix issues!

```bash
# Test with dry-run first
vibe-heal fix src/main.py --dry-run

# Fix a single issue to test
vibe-heal fix src/main.py --max-issues 1

# Fix all MAJOR and above issues
vibe-heal fix src/main.py --min-severity MAJOR
```

## Development Setup

For developers contributing to vibe-heal:

### 1. Clone and Install

```bash
git clone https://github.com/alexeieleusis/vibe-heal.git
cd vibe-heal

# Install with uv
make install
```

### 2. Run Tests

```bash
# Run all tests
make test

# Run with coverage
uv run pytest --cov=src/vibe_heal

# Run specific module tests
uv run pytest tests/config/ -v
uv run pytest tests/sonarqube/ -v
```

### 3. Type Checking and Linting

```bash
# Run type checking
make check

# Run all pre-commit hooks
uv run pre-commit run -a
```

### 4. Development Commands

See [CLAUDE.md](CLAUDE.md) for detailed development commands and project structure.

## Configuration

Create a `.env.vibeheal` file with:

```bash
# SonarQube Configuration (Required)
SONARQUBE_URL=https://sonarqube.example.com
SONARQUBE_TOKEN=your_token_here
# OR use username/password (token is preferred)
# SONARQUBE_USERNAME=your_username
# SONARQUBE_PASSWORD=your_password

SONARQUBE_PROJECT_KEY=your_project_key

# AI Tool Configuration (Optional - will auto-detect if not set)
# AI_TOOL=claude-code  # Use Claude Code
# AI_TOOL=aider        # Use Aider

# Aider-Specific Configuration (only when using Aider)
# AIDER_MODEL=ollama_chat/gemma3:27b          # Model to use
# AIDER_API_KEY=your-api-key                  # API key (if needed)
# AIDER_API_BASE=http://127.0.0.1:11434       # API base URL

# Context Enrichment (Optional - enhances AI fix quality)
# CODE_CONTEXT_LINES=5                        # Lines before/after issue to show AI (default: 5)
# INCLUDE_RULE_DESCRIPTION=true               # Include full rule docs in prompts (default: true)
```

**Example configurations:**

1. **Claude Code** (auto-detected, no extra config needed):
   ```bash
   SONARQUBE_URL=https://sonar.example.com
   SONARQUBE_TOKEN=your_token
   SONARQUBE_PROJECT_KEY=your_project
   ```

2. **Aider with local Ollama**:
   ```bash
   SONARQUBE_URL=https://sonar.example.com
   SONARQUBE_TOKEN=your_token
   SONARQUBE_PROJECT_KEY=your_project
   AI_TOOL=aider
   AIDER_MODEL=ollama_chat/gemma3:27b
   AIDER_API_BASE=http://127.0.0.1:11434
   ```

3. **Aider with OpenAI**:
   ```bash
   SONARQUBE_URL=https://sonar.example.com
   SONARQUBE_TOKEN=your_token
   SONARQUBE_PROJECT_KEY=your_project
   AI_TOOL=aider
   AIDER_MODEL=gpt-4
   AIDER_API_KEY=sk-your-openai-key
   ```

## Project Structure

```
vibe-heal/
├── src/vibe_heal/
│   ├── config/          # Configuration management (✅ Complete)
│   ├── sonarqube/       # SonarQube API client (✅ Complete)
│   ├── ai_tools/        # AI tool integrations (✅ Claude Code + Aider complete)
│   ├── processor/       # Issue processing logic (✅ Complete)
│   ├── git/             # Git operations (✅ Complete)
│   ├── cli.py           # Command-line interface (✅ Complete)
│   ├── orchestrator.py  # Workflow orchestration (✅ Complete)
│   └── models.py        # Top-level models (✅ Complete)
├── tests/               # Comprehensive test suite (157 tests, 82% coverage)
└── docs/                # Documentation and development guides
```

## Contributing

See [docs/ROADMAP.md](docs/ROADMAP.md) for the development roadmap and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system architecture.



---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
