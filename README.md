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

## Current Status: 🚧 In Development

**Completed Phases**:
- ✅ Phase 0: Project Setup
- ✅ Phase 1: Configuration Management (28 tests, 97% coverage)
- ✅ Phase 2: SonarQube API Integration (29 tests, 92% coverage)

**Overall Progress**: 57 tests passing, 90% code coverage

**Next Phase**: Issue Processing Engine

See [ROADMAP.md](docs/ROADMAP.md) for detailed development plan.

## Features (Planned)

- 🔍 Fetch SonarQube issues for any file
- 🤖 AI-powered issue fixing (Claude Code, Aider)
- 📝 Automatic git commits per fix
- 🔄 Smart issue ordering (reverse line order)
- 🛡️ Safe operation (requires clean git state)
- 📊 Detailed progress and summary reports
- 🎯 Support for both SonarQube old and new API formats

## Quick Start (Future)

Once development is complete, using vibe-heal will be as simple as:

```bash
# Install vibe-heal
pip install vibe-heal

# Configure SonarQube connection
cat > .env.vibeheal <<EOF
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token_here
SONARQUBE_PROJECT_KEY=your_project_key
AI_TOOL=claude-code  # or 'aider'
EOF

# Fix issues in a file
vibe-heal fix src/main.py
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
# SonarQube Configuration
SONARQUBE_URL=https://sonarqube.example.com
SONARQUBE_TOKEN=your_token_here
# OR use username/password (token is preferred)
# SONARQUBE_USERNAME=your_username
# SONARQUBE_PASSWORD=your_password

SONARQUBE_PROJECT_KEY=your_project_key

# AI Tool Configuration (optional - will auto-detect if not set)
# AI_TOOL=claude-code
# AI_TOOL=aider
```

## Project Structure

```
vibe-heal/
├── src/vibe_heal/
│   ├── config/          # Configuration management (✅ Complete)
│   ├── sonarqube/       # SonarQube API client (✅ Complete)
│   ├── ai_tools/        # AI tool integrations (🚧 In Progress)
│   ├── processor/       # Issue processing logic (⏳ Pending)
│   ├── git/             # Git operations (⏳ Pending)
│   └── utils/           # Utilities
├── tests/               # Comprehensive test suite (57 tests, 90% coverage)
└── docs/                # Documentation and development guides
```

## Contributing

See [docs/ROADMAP.md](docs/ROADMAP.md) for the development roadmap and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system architecture.



---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
