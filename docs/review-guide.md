# Review Guide

## Overview

The `vibe-heal review` command analyzes SonarQube issues **scoped to the lines you actually changed** in your branch. It is a read-only companion to `cleanup`: instead of fixing issues it reports them, and can post the findings as inline GitHub PR review comments.

The workflow has two phases:

1. **Analyze** (`vibe-heal review`) — create a temporary SonarQube project, run `sonar-scanner`, filter issues to changed lines, and save a `review.json` + `review.md` report.
2. **Post** (`vibe-heal review --post`) — load the saved report and post inline comments to an open GitHub PR via the `gh` CLI.

## When to Use

- Before opening a pull request — catch issues on new/modified lines only (no noise from pre-existing issues).
- During code review — share a structured issue report with reviewers automatically.
- In CI/CD — gate a PR on new SonarQube issues introduced in the diff.

## Prerequisites

### Required for `review` (analyze phase)

1. **sonar-scanner CLI** must be installed
   ```bash
   # macOS
   brew install sonar-scanner

   # Linux — download from https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/
   ```

2. **SonarQube server** with API access and permission to create/delete projects.

3. **git repository** with at least one commit and a reachable base branch.

### Required for `review --post` (post phase)

4. **gh CLI** installed and authenticated
   ```bash
   # macOS
   brew install gh
   gh auth login
   ```

5. An open GitHub Pull Request for the current branch.

### Configuration

Create `.env.vibeheal`:

```bash
# Required
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token_here
SONARQUBE_PROJECT_KEY=your_project_key

# Optional — enriches inline PR comments with rule documentation
INCLUDE_RULE_DESCRIPTION=true  # default: true
```

No AI tool configuration is required for the review command — it only reads, never writes.

## sonar-project.properties Support

If your project has a `sonar-project.properties` file, vibe-heal uses it automatically. Only auth or host-URL flags that are absent from both the file and the environment are appended to the `sonar-scanner` command. All other scanner settings (exclusions, language plugins, coverage paths, etc.) are preserved as-is.

For the temporary SonarQube project created during `review`, vibe-heal patches `sonar.projectKey` and `sonar.projectName` in the file while the scanner runs, then restores the originals. A recovery comment is written first so you can restore manually if the process is interrupted. See the [Branch Cleanup Guide](branch-cleanup-guide.md#sonar-projectproperties-support) for full details.

## Basic Usage

### Analyze changed lines

```bash
# Review all modified files vs origin/main
vibe-heal review

# Compare against a different base branch
vibe-heal review --base-branch origin/develop

# Limit to specific file patterns
vibe-heal review --pattern "src/**/*.py"

# Save report to a custom path
vibe-heal review --report-file /tmp/my-review.json
```

### Post findings to GitHub PR

```bash
# Post saved report as inline PR comments (auto-detects open PR)
vibe-heal review --post

# Preview what would be posted without making API calls
vibe-heal review --post --dry-run

# Specify an explicit PR number
vibe-heal review --post --pr 42

# Load a report from a custom path
vibe-heal review --post --report-file /tmp/my-review.json
```

### Full flags reference

| Flag | Default | Description |
|---|---|---|
| `--base-branch` / `-b` | `origin/main` | Base branch to compare against |
| `--pattern` / `-p` | (all files) | Glob pattern to filter files (repeatable) |
| `--report-file` | auto | Override report output path |
| `--env-file` | `.env.vibeheal` | Path to custom config file |
| `--verbose` / `-v` | off | Enable debug logging |
| `--post` | off | Post saved report to GitHub PR instead of analyzing |
| `--dry-run` | off | With `--post`: preview comments without API calls |
| `--pr` | auto | With `--post`: explicit GitHub PR number |

## How It Works

### Analyze phase

```
1. Detect modified files vs base branch (git three-dot diff)
2. Parse diff to identify changed (new) line numbers per file
3. Create temporary SonarQube project
4. Run sonar-scanner against modified files
5. Fetch issues from temporary project
6. Filter issues to lines that appear in the diff (+ 3-line trailing context)
7. Fetch active duplication blocks intersecting changed lines
8. Detect resolved duplications: blocks that existed on the base branch but
   are no longer active — warns if only one copy was deduplicated
9. Optionally enrich each issue with rule root_cause documentation
10. Write report to ~/.vibe-heal/reviews/<project-key>/<branch>/review.json
    and review.md
11. Delete temporary SonarQube project
12. Display per-file summary table in terminal
```

### Post phase

```
1. Load review.json from default path (or --report-file)
2. Detect open PR via `gh pr list` (or use --pr)
3. Build GitHub Reviews API payload with one inline comment per finding
4. Post review to GitHub PR
```

The two phases are decoupled — you can run `review` in CI and `review --post` locally, or re-post an old report to a new PR.

## Output

### Terminal output (analyze phase)

```
Review Summary:
  Branch: feature/new-api (base: origin/main)
  Files checked: 4
  Total issues: 7
  Duplication findings: 1

Per-File Breakdown:
  File                      Issues  Highest Severity  Duplications
  src/api/users.py               3          CRITICAL             0
  src/api/auth.py                2             MAJOR             1
  src/models/user.py             2             MINOR             0
  tests/test_api.py              0               N/A             0

Report saved to /Users/you/.vibe-heal/reviews/my-project/feature-new-api/review.json
```

### Report files

Two files are written after each analysis:

- **`review.json`** — machine-readable report; includes `root_cause` HTML per issue so `--post` can include rule docs without re-fetching.
- **`review.md`** — human-readable Markdown with issues per file and one collapsed `<details>` block per unique rule (deduped).

Default report directory: `~/.vibe-heal/reviews/<project-key>/<branch>/`

### Inline PR comments (post phase)

Each issue becomes an inline comment anchored to the relevant line. Comments include:

- Issue message and severity
- Rule key and link to SonarQube rule documentation
- A collapsed `<details>` block with the rule's `root_cause` HTML (when `INCLUDE_RULE_DESCRIPTION=true`)

Duplication findings appear as comments noting the other locations where the same code exists.

Resolved duplications (code that was duplicated on the base branch but is no longer duplicated in your branch — possibly meaning you fixed only one copy) appear with a warning to check the remaining copies.

## Duplication Findings

The review command reports two types of duplication findings:

**Active duplications** — code in your changed lines that SonarQube still considers duplicated. The comment shows the other locations where the same block exists.

**Resolved duplications** — code that was duplicated on the base branch and intersects your changed lines, but is no longer flagged as duplicated in your branch. This typically means you refactored one copy of a duplicated block without updating the others. The comment warns you to check the remaining copies.

## Examples

### Example 1: Pre-PR review

```bash
# On feature/payment-redesign
git checkout feature/payment-redesign

# Analyze new issues on changed lines
vibe-heal review

# Open a PR, then post findings inline
gh pr create --title "feat: payment redesign"
vibe-heal review --post
```

### Example 2: Analyze and post in one step (CI)

```bash
# In GitHub Actions
vibe-heal review --base-branch origin/${{ github.base_ref }}
vibe-heal review --post --pr ${{ github.event.pull_request.number }}
```

### Example 3: Preview before posting

```bash
# See what comments would be posted
vibe-heal review --post --dry-run
```

Output:
```
[dry-run] Would post 3 inline comment(s) to PR #42:

  src/api/users.py:87
  **CRITICAL** python:S3776 — Refactor this function to reduce its Cognitive Complexity from 16 to the 15 allowed.
  ...
```

### Example 4: Use a custom base branch and file filter

```bash
vibe-heal review \
  --base-branch origin/develop \
  --pattern "src/**/*.py" \
  --pattern "tests/**/*.py"
```

## CI/CD Integration

### GitHub Actions

```yaml
name: SonarQube Review

on:
  pull_request:

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install sonar-scanner
        run: |
          wget -q https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-6.2.1.4610-linux-x64.zip
          unzip -q sonar-scanner-cli-6.2.1.4610-linux-x64.zip
          sudo mv sonar-scanner-6.2.1.4610-linux-x64 /opt/sonar-scanner
          sudo ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install vibe-heal
        run: pip install vibe-heal

      - name: Create config
        run: |
          cat > .env.vibeheal <<EOF
          SONARQUBE_URL=${{ secrets.SONARQUBE_URL }}
          SONARQUBE_TOKEN=${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY=${{ secrets.SONARQUBE_PROJECT_KEY }}
          EOF

      - name: Analyze changed lines
        run: vibe-heal review --base-branch origin/${{ github.base_ref }}

      - name: Post review comments
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: vibe-heal review --post --pr ${{ github.event.pull_request.number }}
```

## Limitations

1. **Requires sonar-scanner**: Must be installed and on PATH.
2. **Requires SonarQube project permissions**: Create and delete projects.
3. **Requires gh CLI for `--post`**: Must be installed and authenticated.
4. **Open PR required for `--post`**: Auto-detection needs an open PR; use `--pr` to override.
5. **SonarQube `isNew` flag**: The `isNew` field on SonarQube issues is unreliable for branches; vibe-heal uses its own diff-based line filter instead.
6. **Line filter trailing context**: Changed-line clusters expand by 3 lines of trailing context, which may occasionally include issues on lines just after your edits.

## Troubleshooting

### "gh: command not found"

Install the GitHub CLI: <https://cli.github.com/>

```bash
brew install gh
gh auth login
```

### "No open PR found for branch"

Either open a PR first, or use `--pr <number>` to specify one explicitly:

```bash
vibe-heal review --post --pr 42
```

### Report file not found when running `--post`

If you ran `review` with a custom `--report-file`, pass the same path to `--post`:

```bash
vibe-heal review --report-file /tmp/review.json
vibe-heal review --post --report-file /tmp/review.json
```

### "sonar-scanner is not installed or not in PATH"

See the [Branch Cleanup Guide troubleshooting section](branch-cleanup-guide.md#issue-sonar-scanner-is-not-installed-or-not-in-path) for installation instructions.

### No issues reported despite known violations

The review command only reports issues on **changed lines**. Issues on lines you did not touch will not appear. To see all issues for a file:

```bash
vibe-heal fix src/file.py --dry-run
```

## See Also

- [Branch Cleanup Guide](branch-cleanup-guide.md) — automatically fix issues before PR
- [Architecture Documentation](ARCHITECTURE.md)
- [Project Home](index.md)
