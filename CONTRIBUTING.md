# Contributing to `vibe-heal`

Thank you for your interest in contributing to vibe-heal!

## Project Philosophy

vibe-heal is intentionally focused on doing **one thing well**: automatically fixing SonarQube issues using AI tools. We prioritize simplicity, reliability, and maintainability over feature breadth.

**Important**: There are no plans to add heavy new features that would increase complexity or bloat. We prefer incremental improvements to existing functionality over expansive new capabilities.

## Before You Contribute

### For New Features

**IMPORTANT**: Before working on any new feature, you **must** file an issue first to discuss:
- Why the feature is needed
- How it aligns with the project's focused scope
- Whether it adds unnecessary complexity
- Alternative approaches

New features that significantly expand scope or add complexity will likely be declined, even if well-implemented.

### For Bug Fixes

Bug fixes are always welcome! For bugs:
1. Search existing issues first to avoid duplicates
2. Create an issue with reproduction steps
3. Link your PR to the issue

### For Documentation

Documentation improvements are greatly appreciated:
- Fixing typos or clarifying unclear sections
- Adding examples for existing features
- Improving setup instructions

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/alexeieleusis/vibe-heal/issues

Please include:
- Operating system name and version
- Python version
- SonarQube version (if applicable)
- AI tool used (Claude Code or Aider)
- Detailed steps to reproduce the bug
- Expected vs actual behavior

### Fix Bugs

Look through GitHub issues for bugs tagged with "bug" and "help wanted".

### Improve Documentation

Documentation can always be improved:
- Official docs improvements
- Better docstrings
- Example configurations
- Troubleshooting guides

# Get Started!

Ready to contribute? Here's how to set up `vibe-heal` for local development.
Please note this documentation assumes you already have `uv` and `Git` installed and ready to go.

1. Fork the `vibe-heal` repo on GitHub.

2. Clone your fork locally:

```bash
cd <directory_in_which_repo_should_be_created>
git clone git@github.com:YOUR_NAME/vibe-heal.git
```

3. Now we need to install the environment. Navigate into the directory

```bash
cd vibe-heal
```

Then, install and activate the environment with:

```bash
uv sync
```

4. Install pre-commit to run linters/formatters at commit time:

```bash
uv run pre-commit install
```

5. Create a branch for local development:

```bash
git checkout -b name-of-your-bugfix-or-feature
```

Now you can make your changes locally.

6. Don't forget to add test cases for your added functionality to the `tests` directory.

7. When you're done making changes, check that your changes pass the formatting tests.

```bash
make check
```

Now, validate that all unit tests are passing:

```bash
make test
```

9. Before raising a pull request you should also run tox.
   This will run the tests across different versions of Python:

```bash
tox
```

This requires you to have multiple versions of python installed.
This step is also triggered in the CI/CD pipeline, so you could also choose to skip this step locally.

10. Commit your changes and push your branch to GitHub:

```bash
git add .
git commit -m "Your detailed description of your changes."
git push origin name-of-your-bugfix-or-feature
```

11. Submit a pull request through the GitHub website.

# Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. **Issue first**: For new features, you must have discussed the feature in an issue and received approval before submitting a PR.

2. **Tests required**: The pull request must include tests for new functionality or bug fixes.

3. **Documentation**: If the PR changes user-facing behavior, update the relevant documentation.

4. **Keep it focused**: PRs should address a single concern. Large PRs that try to do too much will be asked to be split.

5. **Code quality**: Before submitting, run:
   ```bash
   make check                    # Type checking and linting
   make test                     # Run test suite
   vibe-heal cleanup             # Fix SonarQube issues in your changes
   vibe-heal dedupe-branch       # Remove code duplications
   ```
