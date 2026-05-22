# sonar-project.properties Integration

**Date:** 2026-05-21
**Status:** Approved

## Problem

When `sonar-project.properties` exists in the project directory, vibe-heal ignores it entirely and builds a full sonar-scanner command with explicit `-D` flags. This causes two problems:

1. Configuration values only in the file (custom exclusions, source encoding, analysis scope, language-specific settings) are silently dropped when vibe-heal runs the scanner.
2. When creating a temporary project (review, cleanup, dedupe-branch), the file's `sonar.projectKey` still points at the original project, so the analysis lands in the wrong project.

## Solution Overview

Introduce `SonarPropertiesHandler` — a new class that detects the properties file, builds a minimal scanner command when the file is present, and patches the file's project key/name before scanner invocation (restoring it unconditionally in a `finally` block).

Applies to all commands that run sonar-scanner: `review`, `cleanup`, `dedupe-branch`.

---

## New Component: `SonarPropertiesHandler`

**Location:** `src/vibe_heal/sonarqube/properties_handler.py`

### Command building

`build_command(project_key, project_name, sources) -> list[str]`

- **No properties file present** → returns the existing full `-D` flag command (identical to today, no regression).
- **Properties file present** → returns `["sonar-scanner"]` plus an auth token only as a fallback (see Auth section). Project key, project name, host URL, and sources are all omitted from the command — the file governs them.

### File patching

`patched(project_key, project_name)` — a `contextlib.contextmanager`.

- **On enter:** reads the original file content, detects existing `sonar.projectKey` and `sonar.projectName` lines, comments them out with a recovery header, and inserts the new values above them.
- **On exit (`finally`):** writes the original content back unconditionally.
- **No-op** if the file does not exist, or if the requested `project_key` already matches the `sonar.projectKey` value in the file (key comparison only; name is always updated when key changes).

Patch format:
```
# vibe-heal: temporary analysis project. If this process was interrupted,
# restore the lines below (remove the '#' prefix):
# sonar.projectKey=my-original-project
# sonar.projectName=My Original Project
sonar.projectKey=my-project_user_feature_branch_260521-1430
sonar.projectName=my-project review alexei.eleusis feature-add-login
```

If `sonar.projectName` is not present in the original file, no comment is added for it — the new name line is appended without a paired comment.

### Restore safety net

If the `finally` write-back itself fails (e.g. disk full), the handler logs the original file content at `ERROR` level so the user can manually restore it. It never raises from the restore path so the outer `finally` (temp project deletion) always runs.

---

## Changes to `AnalysisRunner`

`run_analysis()` creates a `SonarPropertiesHandler` scoped to `project_dir` and wraps the scanner invocation:

```python
handler = SonarPropertiesHandler(project_dir, config)
with handler.patched(project_key, project_name):
    command = handler.build_command(project_key, project_name, sources)
    # run sonar-scanner subprocess (unchanged)
```

When the properties file is present and the scanner exits non-zero, `run_analysis()` inspects the combined stdout/stderr for auth-related keywords (`401`, `403`, `Unauthorized`, `Authentication`, case-insensitive). If found, it appends to the error message:

> Hint: authentication may be configured via environment variable (SONAR_TOKEN, SONARQUBE_TOKEN) or the central scanner settings (~/.sonar/sonar-scanner.properties). Check these if you expected auth to be picked up automatically.

---

## Auth Detection

`SonarPropertiesHandler._has_auth_configured() -> bool` checks in order:

1. **Environment variables:** `SONAR_TOKEN`, `SONARQUBE_TOKEN`, `SONAR_LOGIN` — any non-empty value means auth is covered.
2. **Properties file:** scans for non-commented lines matching `sonar.token=`, `sonar.login=`, or `sonar.password=` — any found means auth is covered.

If neither check passes, `build_command` appends the auth flags from config as a fallback (token auth: `-Dsonar.token=…`; basic auth: `-Dsonar.login=…` + `-Dsonar.password=…`).

---

## Changes to `ProjectManager`

`create_temp_project()` gains a `command_name: str` parameter (e.g. `"review"`, `"cleanup"`, `"dedupe-branch"`).

The project **name** (display name in SonarQube UI) is now generated as:

```
{base_key} {command_name} {email_local_part} {branch_with_slashes_as_dashes}
```

Examples:
- `"my-project review alexei.eleusis feature-add-login"`
- `"my-project cleanup alexei.eleusis main"`

The email local part is the portion before `@`. Branch slashes become dashes. The project **key** is unchanged (sanitized alphanumeric, no spaces).

Each calling orchestrator (`ReviewOrchestrator`, `CleanupOrchestrator`, `DedupeBranchOrchestrator`) passes its own command name string.

---

## Data Flow

```
Orchestrator.run_analysis()
  └─ _create_temp_project(command_name="review")      ← new param
       └─ ProjectManager.create_temp_project(...)      ← name format changed
  └─ AnalysisRunner.run_analysis(project_key, ...)
       └─ SonarPropertiesHandler(project_dir, config)  ← new
            ├─ patched(project_key, project_name)       ← patches file in-place
            └─ build_command(...)                       ← minimal or full command
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Properties file absent | Full `-D` command, identical to today |
| Properties file present, auth in env/file | Minimal command, no auth flag injected |
| Properties file present, no auth anywhere | Minimal command + auth flag from config |
| Scanner auth failure + properties file present | Error message + auth hint |
| Restore write-back fails | Log original content at ERROR, continue cleanup |
| Two concurrent vibe-heal runs on same repo | Last writer wins on restore; acceptable edge case |

---

## Testing

- `SonarPropertiesHandler.exists` — with and without file present
- `build_command` — file absent (full command), file present (minimal command), auth fallback injected vs. skipped
- `patched` context manager:
  - File content is patched during `with` block
  - Original restored after normal exit
  - Original restored after exception inside block
  - No-op when file absent
  - No-op when `project_key` already matches file's `sonar.projectKey`
- `_has_auth_configured` — env var present, file property present, neither present, commented-out line in file (must not count)
- Auth failure hint — appended when properties file present and output contains auth keywords; not appended otherwise
- `ProjectManager.create_temp_project` — name includes command, email local part, branch with `/` → `-`
