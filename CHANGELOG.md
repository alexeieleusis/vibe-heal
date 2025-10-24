# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Branch Cleanup Feature** (#10)
  - `vibe-heal cleanup` command for cleaning up all modified files in a branch
  - Git branch analysis to detect modified files vs base branch
  - Temporary SonarQube project creation for isolated analysis
  - SonarQube analysis runner with sonar-scanner CLI integration
  - Iterative fixing workflow until all issues are resolved
  - Automatic temporary project cleanup
  - File pattern filtering support (`--pattern` flag)
  - Configurable iteration limits (`--max-iterations` flag)
  - Base branch selection (`--base-branch` flag, defaults to `origin/main`)
  - Comprehensive user guide with examples and troubleshooting
  - CI/CD integration examples for GitHub Actions and GitLab CI

### Changed

- Updated README.md with cleanup command documentation
- Enhanced project structure to include cleanup module
- Updated test count to 275 tests with 85%+ coverage

### Technical Details

**New Modules**:
- `git/branch_analyzer.py` - Branch comparison and modified file detection
- `sonarqube/project_manager.py` - Temporary project lifecycle management
- `sonarqube/analysis_runner.py` - SonarQube scanner CLI integration
- `cleanup/orchestrator.py` - Branch cleanup workflow orchestration

**CLI Changes**:
- Added `cleanup` command with comprehensive option support
- Helper function `_display_cleanup_results()` for rich output formatting

**Tests**:
- 21 tests for CleanupOrchestrator
- 28 tests for BranchAnalyzer
- 25 tests for ProjectManager and AnalysisRunner
- 12 tests for CLI commands (fix and cleanup)
- Total: 86 new tests added

## [Previous Releases]

### Core Features (Phases 0-6)

- ✅ Project setup and configuration management
- ✅ SonarQube API integration
- ✅ Issue processing engine
- ✅ AI tool integration (Claude Code)
- ✅ Git integration with auto-commit
- ✅ CLI and workflow orchestration
- ✅ Aider integration
- ✅ Context enrichment (rule documentation + code context)
- ✅ Enhanced commit messages

**Test Coverage**: 275 tests, 85%+ coverage

---

## Release Notes Format

For future releases:

### [Version] - YYYY-MM-DD

#### Added
- New features

#### Changed
- Changes to existing functionality

#### Deprecated
- Features to be removed

#### Removed
- Removed features

#### Fixed
- Bug fixes

#### Security
- Security fixes
