# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**vibe-heal** is an AI-powered SonarQube issue remediation tool that automatically fixes code quality problems. The project is initialized from the cookiecutter-uv template and uses modern Python tooling.

## Development Environment

This project uses **uv** as the package manager (not pip or poetry). All Python commands should be run via `uv run`.

### Initial Setup

```bash
make install  # Sets up environment and pre-commit hooks
```

This command:
- Creates virtual environment with `uv sync`
- Installs pre-commit hooks

## Common Commands

### Testing

```bash
# Run all tests with coverage
make test

# Run tests manually
uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

# Run tests across multiple Python versions (requires multiple Python installations)
tox
```

Test files are located in `tests/` directory. When writing tests, remember that `tests/*` files have S101 (assert usage) ignored in ruff configuration.

### Code Quality

```bash
# Run all quality checks (recommended before committing)
make check

# Run pre-commit hooks manually
uv run pre-commit run -a

# Type checking with mypy
uv run mypy

# Check for obsolete dependencies
uv run deptry src
```

### Linting & Formatting

The project uses **ruff** for linting and formatting (not black or flake8). Configuration is in `pyproject.toml`:
- Line length: 120 characters
- Target Python version: 3.9+
- Auto-fix enabled

Pre-commit hooks will automatically run ruff-check and ruff-format on commits.

### Documentation

```bash
# Build and serve docs locally
make docs

# Test documentation build
make docs-test
```

Documentation uses MkDocs with Material theme. Configuration is in `mkdocs.yml`.

### Building

```bash
# Build wheel file
make build

# Clean build artifacts
make clean-build
```

Build uses hatchling as the backend. Package source is in `src/vibe_heal/`.

## Project Structure

- **`src/vibe_heal/`**: Main package source code
- **`tests/`**: Test files (pytest)
- **`docs/`**: MkDocs documentation source
- **`pyproject.toml`**: Project configuration, dependencies, and tool settings
- **`Makefile`**: Common development commands
- **`tox.ini`**: Multi-version Python testing configuration

## Type Checking

mypy is configured with strict settings:
- `disallow_untyped_defs = true`
- `disallow_any_unimported = true`
- Only checks files in `src/`

All functions should have type annotations.

## Testing Philosophy

- Tests should have coverage (`pytest-cov` is configured)
- Coverage reports are generated as XML for codecov integration
- Test discovery uses `testpaths = ["tests"]` in pytest configuration

## Dependencies

Development dependencies are defined in `[dependency-groups]` in `pyproject.toml`. To add dependencies:

```bash
# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>
```

## CI/CD

The project has GitHub Actions workflows for:
- Main workflow on pull requests and pushes to main
- Release workflow when creating releases
- Codecov validation

Workflows use `uv` and are configured in `.github/workflows/`.

## Python Version Support

Supports Python 3.9 through 3.13. The `tox.ini` configuration tests against all these versions.
