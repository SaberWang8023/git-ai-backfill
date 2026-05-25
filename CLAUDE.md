# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`git-ai-backfill` is a CLI tool that marks human-written code as AI-authored in the [git-ai](https://github.com/git-ai-project/git-ai) attribution system. It works by simulating git-ai's checkpoint mechanism.

**Prerequisite**: `git-ai` must be installed and its daemon running. The tool does nothing without it.

## Entry Point

- `bin/git-ai-backfill` — single Python 3 script, no dependencies beyond stdlib. This is also the npm binary entry point.

## Installation

```bash
npm install -g .   # installs `git-ai-backfill` globally via npm
# or run directly:
./bin/git-ai-backfill --help
```

## Two Modes

**`--mode changes`** (default): marks the uncommitted diff of tracked files as AI.
- Runs `git add <file>` then `git-ai checkpoint mock_ai <file>` per file.
- Auto-detects dirty files via `git status --porcelain` if `--files` is omitted.

**`--mode full`**: marks an entire file's content as AI (requires `--files`).
- Replaces file with placeholder lines → `checkpoint mock_known_human` (human baseline) → restores original → `checkpoint mock_ai`.

After either mode, the user must manually run `git commit` to persist the attribution.

## Key Constraints

- `--tool` and `--model` flags are **informational only** — `mock_ai` preset hardcodes `tool="mock_ai"` and `model="unknown"` in the actual git-ai metadata.
- `--mode full` requires `--files`; `--mode changes` auto-detects if `--files` is omitted.
- Files deleted or untracked (`??`) are skipped in auto-detection.
