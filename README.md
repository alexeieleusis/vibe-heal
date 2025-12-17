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
- Creates a version control commit for each successful fix
- Provides detailed progress reporting

## Features

- **Branch cleanup**: Automatically fix all modified files in a branch before code review
- **Code deduplication**: AI-powered removal of duplicate code blocks
- Fetch SonarQube issues for any file
- AI-powered issue fixing with **Claude Code** or **Aider**
- **Enriched AI prompts** with full rule documentation and code context
- Automatic git commits per fix with conventional commit format
- **Enhanced commit messages** with rule links and detailed context
- Smart issue ordering (reverse line order to avoid line number shifts)
- Safe operation (checks for uncommitted changes in target file)
- Detailed progress indicators and summary reports
- Support for both SonarQube old and new API formats
- Dry-run mode for testing without committing
- Configurable severity filtering and issue limits
- AI tool auto-detection (tries Claude Code first, then Aider)
- Aider integration with Ollama/OpenAI/Anthropic support

## Version Control Support

vibe-heal supports both **Git** and **Mercurial** repositories:

- **Git**: Automatically detected via `.git` directory
- **Mercurial**: Automatically detected via `.hg` directory

No configuration required - vibe-heal detects your VCS type automatically.

### Requirements

- **Git users**: `git` command-line tool must be installed
- **Mercurial users**: `hg` command-line tool must be installed
  ```bash
  # Install Mercurial via pip
  pip install mercurial
  ```

When working in a Git repository, vibe-heal will use Git operations. When working in a Mercurial repository, it will automatically use Mercurial operations. All features (fixing issues, deduplication, branch cleanup) work identically with both version control systems.

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

### 4. Fix issues and remove duplications!

**Option A: Fix a single file**
```bash
# Test with dry-run first
vibe-heal fix src/main.py --dry-run

# Fix a single issue to test
vibe-heal fix src/main.py --max-issues 1

# Fix all MAJOR and above issues
vibe-heal fix src/main.py --min-severity MAJOR

# Use a custom environment file
vibe-heal fix src/main.py --env-file .env.production
```

**Option B: Remove code duplications from a file**
```bash
# Remove duplications with dry-run first
vibe-heal dedupe src/main.py --dry-run

# Remove all duplications
vibe-heal dedupe src/main.py

# Limit number of duplications to fix
vibe-heal dedupe src/main.py --max-duplications 5

# Use a custom environment file
vibe-heal dedupe src/main.py --env-file .env.production
```

**Option C: Clean up entire branch** (recommended before code review)
```bash
# Clean up all modified files in your branch
vibe-heal cleanup

# Clean up with custom base branch
vibe-heal cleanup --base-branch develop

# Clean up only Python files
vibe-heal cleanup --pattern "*.py"

# Clean up with more iterations per file
vibe-heal cleanup --max-iterations 20

# Use a custom environment file
vibe-heal cleanup --env-file .env.production
```

**Option D: Remove duplications from entire branch**
```bash
# Remove duplications from all modified files
vibe-heal dedupe-branch

# Remove duplications with custom base branch
vibe-heal dedupe-branch --base-branch develop

# Remove duplications only from Python files
vibe-heal dedupe-branch --pattern "*.py"

# More iterations per file for complex duplications
vibe-heal dedupe-branch --max-iterations 20

# Use a custom environment file
vibe-heal dedupe-branch --env-file .env.production
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

### Default Configuration

By default, vibe-heal looks for configuration in `.env.vibeheal` or `.env` in the current directory.

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

### Custom Environment Files

You can specify a custom environment file using the `--env-file` option:

```bash
# Use a different environment file for production SonarQube
vibe-heal fix src/main.py --env-file .env.production

# Use different configs for different projects
vibe-heal cleanup --env-file ~/configs/project-a.env

# View configuration from a specific file
vibe-heal config --env-file .env.staging
```

This is useful for:
- Managing multiple SonarQube projects
- Switching between different environments (dev, staging, production)
- Testing with different AI tools or configurations
- CI/CD pipelines with environment-specific settings

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
│   ├── config/          # Configuration management
│   ├── sonarqube/       # SonarQube API client
│   ├── ai_tools/        # AI tool integrations (Claude Code + Aider)
│   ├── processor/       # Issue processing logic
│   ├── vcs/             # Version control abstraction (Git & Mercurial)
│   │   ├── git/         # Git implementation
│   │   └── mercurial/   # Mercurial implementation
│   ├── cleanup/         # Branch cleanup orchestration
│   ├── deduplication/   # Code deduplication
│   ├── cli.py           # Command-line interface
│   ├── orchestrator.py  # Workflow orchestration
│   └── models.py        # Top-level models
├── tests/               # Comprehensive test suite
└── docs/                # Documentation
```

## Contributing

Contributions are welcome! However, vibe-heal is intentionally focused on doing one thing well: automatically fixing SonarQube issues using AI tools. There are no plans to add heavy new features that would increase complexity or bloat.

**Before submitting a pull request**:
1. **File an issue first** to discuss your proposed changes
2. Ensure your contribution aligns with the project's focused scope
3. Keep changes simple and well-tested

For bug fixes and improvements to existing functionality, please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system architecture details.



---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
