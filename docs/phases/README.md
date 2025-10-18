# Development Phases

This directory contains detailed implementation plans for each development phase of vibe-heal.

## Phase Overview

| Phase | Name | Status | Dependencies |
|-------|------|--------|--------------|
| 0 | [Project Setup](PHASE_0_SETUP.md) | ✓ Partial | None |
| 1 | [Configuration Management](PHASE_1_CONFIG.md) | Pending | Phase 0 |
| 2 | [SonarQube API Integration](PHASE_2_SONARQUBE.md) | Pending | Phases 0, 1 |
| 3 | [Issue Processing](PHASE_3_PROCESSOR.md) | Pending | Phases 0, 1, 2 |
| 4 | [AI Tool Integration](PHASE_4_AI_TOOLS.md) | Pending | Phases 0, 1, 2, 3 |
| 5 | [Git Integration](PHASE_5_GIT.md) | Pending | Phases 0, 1, 4 |
| 6 | [CLI and Orchestration](PHASE_6_CLI.md) | Pending | Phases 0-5 |
| 7 | [Safety and Polish](PHASE_7_SAFETY.md) | Pending | Phase 6 |

## How to Use These Guides

### For Each Phase:

1. **Read the phase document** to understand objectives and tasks
2. **Check dependencies** - ensure previous phases are complete
3. **Follow tasks sequentially** - they're ordered for a reason
4. **Write tests as you go** - don't defer testing
5. **Verify completion** - use the "Definition of Done" checklist
6. **Run all checks** - tests, type checking, linting

### Development Workflow:

```bash
# 1. Read phase document
cat docs/phases/PHASE_X_NAME.md

# 2. Implement features
# ... write code ...

# 3. Run tests
make test

# 4. Run quality checks
make check

# 5. Verify phase completion
# Check "Definition of Done" in phase document
```

## Phase Dependencies Graph

```
Phase 0: Project Setup
    ↓
Phase 1: Configuration ──────────┐
    ↓                            │
Phase 2: SonarQube API ──────┐   │
    ↓                        │   │
Phase 3: Issue Processing    │   │
    ↓                        │   │
Phase 4: AI Tools ───────────┤   │
    ↓                        │   │
Phase 5: Git Integration ────┘   │
    ↓                            │
Phase 6: CLI & Orchestration ────┘
    ↓
Phase 7: Safety & Polish
```

## Quick Reference

### Phase 0: Project Setup
**Goal**: Install dependencies and create project structure
**Key Deliverables**: Directory structure, dependencies installed

### Phase 1: Configuration
**Goal**: Load and validate configuration from .env files
**Key Deliverables**: `VibeHealConfig`, `AIToolType` enum

### Phase 2: SonarQube API
**Goal**: Fetch issues from SonarQube
**Key Deliverables**: `SonarQubeClient`, `SonarQubeIssue` model

### Phase 3: Issue Processing
**Goal**: Sort and filter issues for fixing
**Key Deliverables**: `IssueProcessor`, reverse line order sorting

### Phase 4: AI Tools
**Goal**: Integrate with Claude Code
**Key Deliverables**: `AITool` base class, `ClaudeCodeTool`, `AIToolFactory`

### Phase 5: Git Integration
**Goal**: Create commits for fixes
**Key Deliverables**: `GitManager`, commit message formatting

### Phase 6: CLI & Orchestration
**Goal**: Wire everything together
**Key Deliverables**: `vibe-heal` CLI, `VibeHealOrchestrator`, end-to-end workflow

### Phase 7: Safety & Polish
**Goal**: Add safety features and improve UX
**Key Deliverables**: Validation, better errors, rollback instructions

## Current Status

- **Completed**: Phase 0 (partial - documentation created)
- **Next**: Complete Phase 0 setup, then move to Phase 1

## Testing Strategy

Each phase includes:
- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test components working together
- **Type checking**: Ensure type safety with mypy
- **Coverage**: Aim for >85% code coverage

## Tips for Success

1. **Don't skip phases** - each builds on the previous
2. **Write tests first** (or at least concurrently)
3. **Use type hints everywhere** - they catch bugs early
4. **Run `make check` frequently** - catch issues early
5. **Commit after each phase** - creates natural checkpoints
6. **Update CLAUDE.md** if you discover important patterns

## Getting Help

- Check [ARCHITECTURE.md](../ARCHITECTURE.md) for design decisions
- Check [ROADMAP.md](../ROADMAP.md) for the big picture
- Each phase document has "Example Usage" sections
- Test files show how components should be used

## Future Phases (Post-V1)

After Phase 7, consider:
- **Phase 8**: Aider integration
- **Phase 9**: Multi-file support
- **Phase 10**: Advanced filtering and customization
- **Phase 11**: Web UI or dashboard

These will be defined based on V1 feedback and usage patterns.
