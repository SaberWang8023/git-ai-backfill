# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目概述

`git-ai-backfill` 是一个 skill，用于在 [git-ai](https://github.com/git-ai-project/git-ai) 归因系统中为漏记的 AI 产出代码补全归因信息。

**前置条件**：必须安装 `git-ai` 并保持其 daemon 运行，否则工具无法工作。

## 入口文件

- `skill/git-ai-backfill/SKILL.md` — skill 定义
- `skill/git-ai-backfill/scripts/git-ai-backfill.py` — Python 3 实现，无第三方依赖

## 两种模式

**`--mode changes`**（默认）：将已追踪文件的未提交改动标记为 AI 产出。

- 对每个文件执行 `git add <file>`，然后通过 stdin 把 `type=ai_agent` 的 JSON 喂给 `git-ai checkpoint agent-v1 --hook-input stdin`。
- 若未指定 `--files`，通过 `git status --porcelain` 自动检测脏文件。

**`--mode full`**：将整个文件内容标记为 AI 产出（需指定 `--files`）。

- 流程：写入占位符 → `checkpoint agent-v1`（`type=human` 人类基线）→ 恢复原始内容 → `checkpoint agent-v1`（`type=ai_agent`）。

两种模式执行完成后，均需手动运行 `git commit` 使归因生效。

## 关键约束

- 底层走 git-ai 的 `agent-v1` preset（见 https://usegitai.com/docs/cli/add-your-agent），是 git-ai 官方「接入自定义 Agent」的标准入口。
- `--tool` 和 `--model` 真正写入归因元数据：`--tool` → `agent_name`、`--model` → `model`。
- `--model` 取值优先级：命令行参数 > 环境变量 `GIT_AI_BACKFILL_MODEL` > 默认值 `mock-ai`。
- `--tool` 取值优先级：命令行参数 > 环境变量 `GIT_AI_BACKFILL_TOOL` > 默认值 `agent`。
- `--mode full` 必须配合 `--files`；`--mode changes` 在未指定 `--files` 时自动检测。
- 已删除（`D`）或未追踪（`??`）的文件在自动检测时会被跳过。
- hook_input 通过 `--hook-input stdin` 传递，文件路径放在 JSON 的 `edited_filepaths` 里（不作为命令行尾部参数，因为 agent-v1 不像 mock_ai 那样从尾部参数合成 hook_input）。
