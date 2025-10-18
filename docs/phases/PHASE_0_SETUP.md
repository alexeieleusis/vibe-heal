# Phase 0: Project Setup ✅ COMPLETE

## Objective

Set up the project structure and install core dependencies needed for development.

## Status: ✅ COMPLETE

- [x] Initialize project with cookiecutter-uv
- [x] Create CLAUDE.md
- [x] Create ROADMAP.md
- [x] Create ARCHITECTURE.md
- [x] Add core dependencies
- [x] Set up project structure (directories and **init**.py files)
- [x] Remove template example code
- [x] Create .env.vibeheal.example
- [x] Update .gitignore

**Completed**: Successfully set up project structure with all required dependencies and documentation.

## Tasks

### 1. Add Core Dependencies

Add the following dependencies to `pyproject.toml`:

**Runtime dependencies**:

```bash
uv add python-dotenv pydantic pydantic-settings httpx typer rich GitPython
```

**Development dependencies** (if not already present):

```bash
uv add --dev pytest-mock pytest-asyncio responses
```

**Dependency breakdown**:

- `python-dotenv` - Load environment variables from .env files
- `pydantic` - Data validation and settings management
- `pydantic-settings` - Settings management with env var support
- `httpx` - Modern async HTTP client for SonarQube API
- `typer` - CLI framework
- `rich` - Beautiful terminal output (progress bars, tables, etc.)
- `GitPython` - Git operations
- `pytest-mock` - Mocking support for tests
- `pytest-asyncio` - Async test support
- `responses` - HTTP response mocking

### 2. Create Project Structure

Create the module structure:

```bash
# Main package structure
mkdir -p src/vibe_heal/{config,sonarqube,ai_tools,git,processor,utils}

# Create __init__.py files
touch src/vibe_heal/config/__init__.py
touch src/vibe_heal/sonarqube/__init__.py
touch src/vibe_heal/ai_tools/__init__.py
touch src/vibe_heal/git/__init__.py
touch src/vibe_heal/processor/__init__.py
touch src/vibe_heal/utils/__init__.py

# Create test structure
mkdir -p tests/{config,sonarqube,ai_tools,git,processor,utils}
touch tests/config/__init__.py
touch tests/sonarqube/__init__.py
touch tests/ai_tools/__init__.py
touch tests/git/__init__.py
touch tests/processor/__init__.py
touch tests/utils/__init__.py
```

### 3. Remove Template Example Code

Remove the example code from the template:

- Delete `src/vibe_heal/foo.py`
- Delete `tests/test_foo.py`
- Update `src/vibe_heal/__init__.py` to be minimal

### 4. Update Package Metadata

Update `pyproject.toml` to reflect the actual project:

- Ensure `name = "vibe-heal"` is correct
- Update description if needed
- Add any missing keywords

### 5. Create .env.example

Create `.env.vibeheal.example` file with template configuration:

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

### 6. Update .gitignore

Ensure `.gitignore` includes:

```
.env
.env.*
!.env.vibeheal.example
```

## Verification Steps

After completing this phase:

1. Dependencies installed:

   ```bash
   uv run python -c "import pydantic, httpx, typer, rich, git, dotenv; print('All dependencies OK')"
   ```

2. Project structure exists:

   ```bash
   ls -la src/vibe_heal/
   # Should show: config, sonarqube, ai_tools, git, processor, utils
   ```

3. Tests run (even if empty):

   ```bash
   make test
   # Should pass with no tests collected or minimal tests
   ```

4. Type checking passes:
   ```bash
   make check
   ```

## Definition of Done

- ✅ All dependencies installed and importable
- ✅ Directory structure created
- ✅ Template example code removed
- ✅ `.env.vibeheal.example` created
- ✅ All pre-commit hooks pass
- ✅ `make test` and `make check` pass
- ✅ Ready to start implementing Phase 1

## Notes

- Keep this phase simple - just structure and dependencies
- Don't write any business logic yet
- Ensure clean state before proceeding to Phase 1
