# vibe-heal

[![Release](https://img.shields.io/github/v/release/alexeieleusis/vibe-heal)](https://img.shields.io/github/v/release/alexeieleusis/vibe-heal)
[![Build status](https://img.shields.io/github/actions/workflow/status/alexeieleusis/vibe-heal/main.yml?branch=main)](https://github.com/alexeieleusis/vibe-heal/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/alexeieleusis/vibe-heal)](https://img.shields.io/github/commit-activity/m/alexeieleusis/vibe-heal)
[![License](https://img.shields.io/github/license/alexeieleusis/vibe-heal)](https://img.shields.io/github/license/alexeieleusis/vibe-heal)

AI-powered SonarQube issue remediation that automatically fixes your code quality problems using Claude Code or Aider.

## Features

- **Branch cleanup**: Automatically fix all modified files in a branch before code review
- **Code deduplication**: AI-powered removal of duplicate code blocks
- **Branch review**: Report SonarQube issues scoped to changed lines and post inline GitHub PR comments
- AI-powered issue fixing with **Claude Code** or **Aider**
- **Enriched AI prompts** with full rule documentation and code context
- Automatic git commits per fix with conventional commit format
- Smart issue ordering (reverse line order to avoid line number shifts)
- Support for both SonarQube old and new API formats
- Dry-run mode for testing without committing
- AI tool auto-detection (tries Claude Code first, then Aider)

## Commands

| Command | Description |
|---|---|
| `vibe-heal fix <file>` | Fix SonarQube issues in a single file |
| `vibe-heal dedupe <file>` | Remove code duplications from a single file |
| `vibe-heal cleanup` | Fix all modified files in the current branch |
| `vibe-heal dedupe-branch` | Remove duplications from all modified files in the current branch |
| `vibe-heal review` | Report issues on changed lines; optionally post to GitHub PR |
| `vibe-heal config` | Show current configuration |
| `vibe-heal version` | Show version information |

## Quick Links

- [Branch Cleanup Guide](branch-cleanup-guide.md) — full guide for the `cleanup` and `dedupe-branch` commands
- [Review Guide](review-guide.md) — full guide for the `review` command and GitHub PR commenting
- [Architecture](ARCHITECTURE.md) — system design and module structure
