# Branch Cleanup Guide

## Overview

The `vibe-heal cleanup` command automatically fixes all SonarQube issues in modified files of your feature branch before code review. This ensures pull requests have no new code quality issues.

## When to Use

Use `vibe-heal cleanup` when:

- 🔍 **Before creating a pull request** - Ensure your branch is clean
- ✨ **After implementing a feature** - Clean up any issues introduced
- 🚀 **In CI/CD pipelines** - Automatically fix issues before merge
- 📝 **During code review** - Address quality issues systematically

## How It Works

1. **Analyzes branch**: Compares current branch against base branch (default: `origin/main`)
2. **Creates temporary project**: Creates a unique SonarQube project for analysis
3. **Runs analysis**: Analyzes all modified files using `sonar-scanner`
4. **Fixes issues iteratively**: For each file:
   - Runs SonarQube analysis
   - Gets fixable issues
   - Fixes all issues using AI tool
   - Creates git commits for each fix
   - Repeats until no fixable issues remain (or max iterations reached)
5. **Cleans up**: Deletes temporary SonarQube project

## Prerequisites

### Required

1. **sonar-scanner CLI** must be installed
   ```bash
   # macOS
   brew install sonar-scanner

   # Linux
   # Download from https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/
   ```

2. **SonarQube server** with API access

3. **AI tool** installed (Claude Code or Aider)

4. **Git repository** with remote branches

5. **SonarQube user permissions**:
   - Create projects (`POST /api/projects/create`)
   - Delete projects (`POST /api/projects/delete`)
   - Run analysis

### Configuration

Create `.env.vibeheal`:

```bash
# Required
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token_here
SONARQUBE_PROJECT_KEY=your_project_key

# Optional - AI tool will be auto-detected if not specified
AI_TOOL=claude-code  # or "aider"
```

## Basic Usage

### Clean up current branch

```bash
# Clean up all modified files
vibe-heal cleanup
```

This will:
- Compare against `origin/main`
- Fix all modified files
- Run up to 10 iterations per file
- Create git commits for each fix

### Specify base branch

```bash
# Compare against develop branch
vibe-heal cleanup --base-branch origin/develop

# Compare against a specific branch
vibe-heal cleanup --base-branch origin/release-1.0
```

### Filter by file patterns

```bash
# Only clean up Python files
vibe-heal cleanup --pattern "*.py"

# Clean up multiple patterns
vibe-heal cleanup --pattern "*.py" --pattern "*.ts"

# Clean up specific directory
vibe-heal cleanup --pattern "src/**/*.py"
```

### Adjust iteration limit

```bash
# More iterations for stubborn issues
vibe-heal cleanup --max-iterations 20

# Fewer iterations for quick cleanup
vibe-heal cleanup --max-iterations 5
```

### Specify AI tool

```bash
# Use Claude Code explicitly
vibe-heal cleanup --ai-tool claude-code

# Use Aider explicitly
vibe-heal cleanup --ai-tool aider
```

### Verbose output

```bash
# Enable verbose logging
vibe-heal cleanup --verbose
```

## Examples

### Example 1: Pre-PR cleanup

```bash
# You're on feature/new-api branch
git checkout feature/new-api

# Clean up all modified files before creating PR
vibe-heal cleanup

# Output:
# Branch Cleanup
#   Base branch: origin/main
#   Max iterations per file: 10
#
# Auto-detected AI tool: Claude Code
#
# Cleanup Summary:
#   Files processed: 5
#   Total issues fixed: 23
#
# Per-File Results:
#   ✓ src/api/users.py: 8 issues fixed
#   ✓ src/api/auth.py: 5 issues fixed
#   ✓ src/models/user.py: 4 issues fixed
#   ✓ src/utils/validation.py: 6 issues fixed
#   ✓ tests/test_api.py: 0 issues fixed
#
# ✨ Branch cleanup complete!
```

### Example 2: Clean up only backend files

```bash
# Only fix Python files in src/ directory
vibe-heal cleanup --pattern "src/**/*.py"
```

### Example 3: Clean up with custom base and more iterations

```bash
# Compare against develop, allow more iterations
vibe-heal cleanup --base-branch origin/develop --max-iterations 15
```

## Output and Results

### Success Output

```
Branch Cleanup
  Base branch: origin/main
  Max iterations per file: 10

Using configured AI tool: Claude Code

Cleanup Summary:
  Files processed: 3
  Total issues fixed: 12

Per-File Results:
  ✓ src/file1.py: 5 issues fixed
  ✓ src/file2.py: 7 issues fixed
  ✓ src/file3.py: 0 issues fixed

✨ Branch cleanup complete!
```

### Failure Output

```
Branch Cleanup
  Base branch: origin/main
  Max iterations per file: 10

Using configured AI tool: Claude Code

Cleanup Summary:
  Files processed: 2
  Total issues fixed: 5

Per-File Results:
  ✓ src/file1.py: 5 issues fixed
  ✗ src/file2.py: 0 issues fixed
      Error: Analysis failed at iteration 1: Analysis failed

Cleanup failed: 1 fixes failed
```

### Git Commits

Each fix creates a separate git commit:

```
fix: [python:S1234] Remove unused import

SonarQube Issue: https://sonar.example.com/issues?id=issue-key
Rule: python:S1234
Severity: MAJOR
File: src/api/users.py:15

Message: Remove this unused import of 'datetime'

Fixed by: Claude Code

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Troubleshooting

### Issue: "sonar-scanner is not installed or not in PATH"

**Solution**: Install sonar-scanner CLI

```bash
# macOS
brew install sonar-scanner

# Linux - download from official site
wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
unzip sonar-scanner-cli-5.0.1.3006-linux.zip
sudo mv sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner
sudo ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner
```

### Issue: "No AI tool found"

**Solution**: Install an AI tool

```bash
# Option A: Install Claude Code
# See https://docs.claude.com/claude-code

# Option B: Install Aider
pip install aider-chat
```

### Issue: "Authentication failed. Check your credentials"

**Solution**: Verify your SonarQube token

```bash
# Test token manually
curl -u "your_token:" https://sonar.example.com/api/system/status

# If using username/password
curl -u "username:password" https://sonar.example.com/api/system/status
```

### Issue: "API request failed: Project already exists"

**Cause**: A previous cleanup didn't finish properly and left a temp project

**Solution**: Manually delete the temp project

1. Go to SonarQube web UI → Administration → Projects
2. Search for projects with your email and branch name
3. Delete the orphaned project

Or use the API:

```bash
# List projects
curl -u "your_token:" "https://sonar.example.com/api/projects/search"

# Delete specific project
curl -u "your_token:" -X POST "https://sonar.example.com/api/projects/delete?project=PROJECT_KEY"
```

### Issue: "Analysis timed out or failed on server"

**Possible causes**:
- Large project taking too long
- SonarQube server is busy
- Network issues

**Solutions**:
1. Check SonarQube server status
2. Try cleaning up fewer files with `--pattern`
3. Check SonarQube server logs for errors
4. Increase timeout (currently hardcoded to 300s - contact maintainers if needed)

### Issue: Files not being detected

**Cause**: Modified files not in git

**Solution**: Ensure files are tracked by git

```bash
# Check what git sees as modified
git diff --name-only origin/main...HEAD

# Add files to git
git add <files>
git commit -m "WIP: changes to clean up"

# Then run cleanup
vibe-heal cleanup
```

### Issue: Max iterations reached but issues still remain

**Possible causes**:
- Issues are not actually fixable by AI
- AI tool is having trouble understanding the issue
- Complex issues requiring manual intervention

**Solutions**:
1. Increase max iterations: `--max-iterations 20`
2. Check which specific issues remain:
   ```bash
   vibe-heal fix src/file.py --dry-run
   ```
3. Fix manually and commit
4. Review the issue in SonarQube to understand why it can't be fixed

## Best Practices

### 1. Run cleanup regularly

```bash
# After implementing a feature
vibe-heal cleanup

# Before creating a PR
vibe-heal cleanup

# After rebasing
vibe-heal cleanup
```

### 2. Use file patterns for large branches

For branches with many modified files, clean up incrementally:

```bash
# First, clean up backend
vibe-heal cleanup --pattern "src/backend/**/*.py"

# Then frontend
vibe-heal cleanup --pattern "src/frontend/**/*.ts"

# Finally, tests
vibe-heal cleanup --pattern "tests/**/*.py"
```

### 3. Review commits after cleanup

```bash
# After cleanup completes
git log --oneline -20

# Review changes
git diff HEAD~10..HEAD

# If needed, squash cleanup commits
git rebase -i origin/main
```

### 4. Test after cleanup

```bash
# Run tests to ensure nothing broke
make test

# Run linters
make check

# Manual testing of affected features
```

### 5. Use in CI/CD

See [CI/CD Integration](#cicd-integration) section below.

## Advanced Usage

### Cleanup specific files only

While `cleanup` is designed for all modified files, you can combine patterns to target specific files:

```bash
# Only files in src/api/
vibe-heal cleanup --pattern "src/api/**/*.py"

# Only test files
vibe-heal cleanup --pattern "tests/**/*.py"

# Multiple patterns
vibe-heal cleanup --pattern "src/**/*.py" --pattern "tests/**/*.py"
```

### Dry-run equivalent

There's no dry-run for `cleanup` command, but you can:

1. Run analysis manually:
   ```bash
   # For each modified file
   vibe-heal fix src/file.py --dry-run
   ```

2. Check what would be cleaned:
   ```bash
   # See modified files
   git diff --name-only origin/main...HEAD
   ```

### Cleanup after rebase

```bash
# After rebasing
git rebase origin/main

# Fix any new issues introduced
vibe-heal cleanup
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Branch Cleanup

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Need full history for branch comparison

      - name: Install sonar-scanner
        run: |
          wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
          unzip sonar-scanner-cli-5.0.1.3006-linux.zip
          sudo mv sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner
          sudo ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install vibe-heal
        run: pip install vibe-heal

      - name: Create config
        run: |
          cat > .env.vibeheal <<EOF
          SONARQUBE_URL=${{ secrets.SONARQUBE_URL }}
          SONARQUBE_TOKEN=${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY=${{ secrets.SONARQUBE_PROJECT_KEY }}
          AI_TOOL=claude-code
          EOF

      - name: Run cleanup
        run: vibe-heal cleanup --base-branch origin/${{ github.base_ref }}

      - name: Push changes
        run: |
          git config user.name "vibe-heal[bot]"
          git config user.email "vibe-heal[bot]@users.noreply.github.com"
          git push
```

### GitLab CI

```yaml
cleanup:
  stage: quality
  image: python:3.11
  before_script:
    - apt-get update && apt-get install -y wget unzip
    - wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
    - unzip sonar-scanner-cli-5.0.1.3006-linux.zip
    - mv sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner
    - ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner
    - pip install vibe-heal
  script:
    - |
      cat > .env.vibeheal <<EOF
      SONARQUBE_URL=${SONARQUBE_URL}
      SONARQUBE_TOKEN=${SONARQUBE_TOKEN}
      SONARQUBE_PROJECT_KEY=${SONARQUBE_PROJECT_KEY}
      AI_TOOL=claude-code
      EOF
    - vibe-heal cleanup --base-branch origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME
    - git push origin HEAD:$CI_COMMIT_REF_NAME
  only:
    - merge_requests
```

## Limitations

1. **Requires sonar-scanner**: Must have sonar-scanner CLI installed
2. **Network access**: Needs access to SonarQube server
3. **Project permissions**: Needs permission to create/delete projects
4. **AI tool availability**: Requires Claude Code or Aider installed
5. **Git state**: Files must be committed to git to be detected
6. **Iterative approach**: May not fix all issues in one pass (hence max iterations)
7. **No rollback**: No built-in rollback mechanism (use git reset)

## FAQ

### Q: Can I run cleanup without committing?

**A**: No, cleanup is designed to create commits for each fix. If you want to preview without committing, use `vibe-heal fix <file> --dry-run` on individual files first.

### Q: How many iterations are enough?

**A**: Default is 10, which should handle most cases. If issues persist:
- Increase to 15-20 for complex issues
- Check if issues are actually fixable
- Review remaining issues manually

### Q: Can I cancel cleanup mid-way?

**A**: Yes, press Ctrl+C. The temporary project will be cleaned up, and commits made so far will remain.

### Q: What happens if my internet connection drops?

**A**: The cleanup will fail, but:
- Commits made before the failure remain
- Temporary project should be cleaned up in finally block
- If temp project remains, manually delete it (see Troubleshooting)

### Q: Can I use cleanup on main branch?

**A**: Technically yes, but **not recommended**. Cleanup is designed for feature branches before merging to main.

### Q: Does cleanup affect my working directory?

**A**: Yes, it modifies files and creates commits. Ensure you don't have uncommitted changes you care about.

### Q: Can I customize the commit messages?

**A**: Not currently. Commit messages follow a standard format. Feature request: #TBD

## See Also

- [Configuration Guide](../README.md#configuration)
- [Fix Command Documentation](../README.md#quick-start)
- [Architecture Documentation](ARCHITECTURE.md)
- [CI/CD Integration Examples](#cicd-integration)
