# Design: Copy Exclusion Settings to Temporary SonarQube Projects

**Date:** 2026-05-11
**Status:** Approved
**Commands affected:** `vibe-heal cleanup`, `vibe-heal dedupe-branch`

## Problem

When `cleanup` or `dedupe-branch` run, they create a fresh temporary SonarQube project
(`ProjectManager.create_temp_project()`). This blank project inherits none of the exclusion
settings from the original project — in particular `sonar.cpd.exclusions` (files to ignore
for code duplication). As a result, the analysis reports duplication issues on files that
the original project intentionally excludes, and the AI tool attempts to fix them
unnecessarily.

## Goal

After creating the temporary project, copy the source project's exclusion settings to it so
the temp project's analysis behavior matches the original as closely as possible.

## Scope

### Settings copied

The following SonarQube settings keys are copied:

- `sonar.exclusions` — source files excluded from analysis
- `sonar.test.exclusions` — test files excluded from analysis
- `sonar.coverage.exclusions` — files excluded from coverage
- `sonar.cpd.exclusions` — files excluded from duplication detection
- `sonar.inclusions` — source files included (restricts scope)
- `sonar.test.inclusions` — test files included

Only settings **explicitly set on the source project** (not inherited from global defaults)
are copied. The `inherited` flag from the SonarQube API is used to distinguish these.

### Out of scope

Quality gates, quality profiles, permissions, and all other non-exclusion settings are not
copied. The temp project is short-lived and these settings would add complexity without
meaningful benefit.

## Error handling

Copying settings is best-effort. If the fetch or write fails for any reason (insufficient
API permissions, unsupported SonarQube version, network error), the orchestrator logs a
yellow warning and proceeds. The temp project will have no exclusions, which is the current
behavior.

## Architecture

### Approach selected: Approach B — new `copy_exclusion_settings()` on `ProjectManager`

`create_temp_project()` is left unchanged. Settings transfer is a separate, explicit step
called by orchestrators after project creation. This keeps creation and configuration as
distinct, independently testable concerns.

## Component changes

### 1. `SonarQubeClient` (`src/vibe_heal/sonarqube/client.py`)

Two new async methods:

```python
async def get_project_settings(self, project_key: str) -> list[dict]:
    """GET /api/settings/values?component=<project_key>
    Returns the raw list of setting dicts from the API response."""

async def set_project_setting(
    self, project_key: str, setting_key: str, values: list[str]
) -> None:
    """POST /api/settings/set
    Uses multi-value form since exclusion settings are always path-pattern lists."""
```

Both scalar (`value`) and multi-value (`values`) shapes returned by the API are normalised
to `list[str]` before `set_project_setting` is called.

### 2. `ProjectManager` (`src/vibe_heal/sonarqube/project_manager.py`)

Class-level constant:

```python
EXCLUSION_SETTINGS: ClassVar[tuple[str, ...]] = (
    "sonar.exclusions",
    "sonar.test.exclusions",
    "sonar.coverage.exclusions",
    "sonar.cpd.exclusions",
    "sonar.inclusions",
    "sonar.test.inclusions",
)
```

New method:

```python
async def copy_exclusion_settings(
    self, source_key: str, target_key: str
) -> tuple[list[str], int, int]:
    """Copy exclusion settings from source project to target project.

    Steps:
    1. GET /api/settings/values?component=source_key
    2. Filter to EXCLUSION_SETTINGS keys that are not inherited
    3. POST each to the target project
    4. Return tuple of (list of keys that were copied, count of inherited keys skipped,
       count of keys that failed to apply)

    Raises SonarQubeError if the fetch step fails (caller handles warn-and-continue).
    Individual set failures are logged and counted, not re-raised.
    """
```

### 3. `CleanupOrchestrator._create_temp_project()` (`src/vibe_heal/cleanup/orchestrator.py`)

After the existing `create_temp_project()` call:

```python
try:
    copied, inherited_count, failed_count = await self.project_manager.copy_exclusion_settings(
        source_key=self.config.sonarqube_project_key,
        target_key=temp_project.project_key,
    )
    if copied:
        console.print(f"[dim]Copied {len(copied)} exclusion setting(s): {', '.join(copied)}[/dim]")
    if inherited_count:
        console.print(f"[dim]Skipped {inherited_count} inherited setting(s)[/dim]")
    if failed_count:
        console.print(f"[yellow]Warning: Failed to apply {failed_count} exclusion setting(s)[/yellow]")
    if not copied and not inherited_count and not failed_count:
        console.print("[dim]No exclusion settings configured on source project[/dim]")
except SonarQubeError as e:
    console.print(f"[yellow]Warning: Could not copy exclusion settings: {e}[/yellow]")
```

### 4. `DedupeBranchOrchestrator._create_temp_project()` (`src/vibe_heal/deduplication/orchestrator.py`)

Identical addition as Section 3 above, but using `self.console.print()` instead of the module-level `console.print()`.

## Data flow

```
cleanup / dedupe-branch
    └─ _create_temp_project()
           ├─ project_manager.create_temp_project()   [unchanged]
           └─ project_manager.copy_exclusion_settings(source, target)
                  ├─ client.get_project_settings(source)
                  │      GET /api/settings/values?component=source
                  ├─ filter: key in EXCLUSION_SETTINGS and not inherited
                  └─ for each matching setting:
                         client.set_project_setting(target, key, values)
                                POST /api/settings/set
```

## Testing

### `tests/sonarqube/test_client.py`

- `test_get_project_settings` — mocks `_request`; asserts raw list returned correctly for
  both scalar and multi-value setting shapes
- `test_set_project_setting` — asserts POST called with correct params (multi-value form)

### `tests/sonarqube/test_project_manager.py`

- `test_copy_exclusion_settings_copies_non_inherited` — source has 3 settings, one
  inherited; asserts only 2 non-inherited ones are applied to target
- `test_copy_exclusion_settings_returns_empty_when_none_match` — source settings contain
  none of the EXCLUSION_SETTINGS keys; asserts `([], 0)` returned, no set calls made
- `test_copy_exclusion_settings_raises_if_fetch_fails` — `get_project_settings` raises
  `SonarQubeAPIError`; asserts the error propagates out of `copy_exclusion_settings`
  (callers own the warn-and-continue, not this method)

### `tests/cleanup/test_orchestrator.py`

- `test_create_temp_project_warns_on_settings_copy_failure` — `copy_exclusion_settings`
  raises; asserts orchestrator prints yellow warning and does not re-raise

### `tests/deduplication/test_branch_orchestrator.py`

- `test_create_temp_project_warns_on_settings_copy_failure` — same as above for the dedupe
  branch orchestrator
