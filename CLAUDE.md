# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目概述

`git-ai-backfill` 是一个 CLI 工具，用于在 [git-ai](https://github.com/git-ai-project/git-ai) 归因系统中为漏记的 AI 产出代码补全归因信息。它通过模拟 git-ai 的 checkpoint 机制实现。

**前置条件**：必须安装 `git-ai` 并保持其 daemon 运行，否则工具无法工作。

## 开发规范

**永远先修改源码 `git-ai-backfill.py`，再将改动同步到 `bin/git-ai-backfill`。**

## 入口文件

- `git-ai-backfill.py` — Python 3 源码，无第三方依赖
- `bin/git-ai-backfill` — 由源码同步而来的可执行文件，也是 npm binary 入口

## 安装

```bash
npm install -g .   # 全局安装 git-ai-backfill 命令
# 或直接运行：
./bin/git-ai-backfill --help
```

## 两种模式

**`--mode changes`**（默认）：将已追踪文件的未提交改动标记为 AI 产出。
- 对每个文件执行 `git add <file>`，然后执行 `git-ai checkpoint claude --hook-input <json> <file>`。
- 若未指定 `--files`，通过 `git status --porcelain` 自动检测脏文件。

**`--mode full`**：将整个文件内容标记为 AI 产出（需指定 `--files`）。
- 流程：写入占位符 → `checkpoint mock_known_human`（人类基线）→ 恢复原始内容 → `checkpoint claude --hook-input <json>`。

两种模式执行完成后，均需手动运行 `git commit` 使归因生效。

## 关键约束

- `--tool` 和 `--model` 参数真正写入归因元数据，通过 `--hook-input` 传给 `git-ai checkpoint claude`。
- `--model` 取值优先级：命令行参数 > 环境变量 `GIT_AI_BACKFILL_MODEL` > 默认值 `claude-sonnet-4.6`。
- `--tool` 取值优先级：命令行参数 > 环境变量 `GIT_AI_BACKFILL_TOOL` > 默认值 `claude`。
- `--mode full` 必须配合 `--files`；`--mode changes` 在未指定 `--files` 时自动检测。
- 已删除（`D`）或未追踪（`??`）的文件在自动检测时会被跳过。
