---
name: git-ai-backfill
description: 为不支持 git-ai hooks 的 Agent（如 OpenClaw、Hermes 等）产出的 AI 代码补全归因记录。当用户说"把这段代码标记为 AI 写的"、"这个 Agent 没有 hooks 支持"、"补全 git-ai 归因"、"backfill attribution"、"这是 AI 生成的但没被记录"时使用此 skill。只要用户提到 git-ai 归因缺失、AI 代码漏记、或想补填 checkpoint，就应使用此 skill。
---

# git-ai-backfill

通过 `git-ai-backfill` CLI 工具，利用 git-ai 的 checkpoint 机制，为因 Agent 不支持 hooks 而漏记的 AI 代码补全归因信息。

## 前置条件

- git-ai 已安装并在 PATH 中
- 当前目录是 git 仓库
- git-ai daemon 正在运行

如未安装 git-ai，告知用户前往 https://usegitai.com/ 安装。

## 使用时机

当用户表达以下意图时使用此 skill：

- "把这些改动补填为 AI 的归因"
- "这段代码是 AI 写的但没有被记录"
- "补全 git-ai 归因"
- "backfill ai attribution"
- "这个 Agent 不支持 hooks，帮我补填归因"
- "OpenClaw / Hermes 写的代码没被 git-ai 记录"

## 工作流

### 第 1 步：确认用户意图和范围

在执行任何操作前，向用户确认：

1. **目标文件**：哪些文件需要标记？还是自动检测所有未提交的改动？
2. **操作模式**：
   - `changes`（默认）：只标记未提交的改动（适合已修改但未提交的文件）
   - `full`：标记整个文件内容为 AI 产出（适合新文件）
3. **模型信息**（可选）：使用的 AI 工具和模型，默认 `tool=agent`、`model=mock-ai`

### 第 2 步：预览操作（dry-run）

**必须先执行 dry-run 让用户确认**：

```bash
git-ai-backfill --mode changes --dry-run
# 或
git-ai-backfill --mode full --files <file1> <file2> --dry-run
```

向用户展示 dry-run 输出，等待确认。

### 第 3 步：执行标记

用户确认后，执行实际操作：

```bash
# 标记未提交的改动
git-ai-backfill --mode changes

# 标记整个文件
git-ai-backfill --mode full --files <file>

# 指定模型信息
git-ai-backfill --mode changes --tool claude --model claude-sonnet-4.6
```

### 第 4 步：提示用户提交

脚本执行后**不会自动提交**，告知用户手动完成：

```bash
git commit -m "your commit message"
```

### 第 5 步：验证结果（可选）

提交后可验证归属是否正确：

```bash
git-ai blame <file>
git-ai stats HEAD --json
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mode` | `changes` | 操作模式：`changes` 或 `full` |
| `--files` | 自动检测 | 目标文件路径 |
| `--tool` | `agent`（或 `GIT_AI_BACKFILL_TOOL` 环境变量） | AI 工具名，写入归因元数据 |
| `--model` | `mock-ai`（或 `GIT_AI_BACKFILL_MODEL` 环境变量） | AI 模型名，写入归因元数据 |
| `--session` | 自动生成 | 自定义会话 ID |
| `--dry-run` | 关闭 | 预览模式，不实际执行 |

## 注意事项

1. **`--mode full` 必须配合 `--files`**：不能自动检测，需明确指定文件
2. **不自动提交**：脚本只创建 checkpoint，用户需手动 `git commit`
3. **归属边界效应**：git diff 的 hunk 边界可能导致相邻未修改行被意外归为 AI，这是 git-ai 的固有行为
4. **tool/model 写入元数据**：通过 `--hook-input` 传给 `git-ai checkpoint claude`，真正写入归因记录

## 示例交互

```
用户: 我用 OpenClaw 写了一些代码，但它没有 git-ai hooks，帮我补填归因

AI: 我来帮你补填。先预览一下会操作哪些文件：
    [执行] git-ai-backfill --mode changes --dry-run
    [展示输出]
    确认执行吗？

用户: 确认

AI: [执行] git-ai-backfill --mode changes
    完成。请执行以下命令提交使归因生效：
    git commit -m "your message"
```

## 不适用场景

- 修改已有提交的归属（需要 `git commit --amend` 或 `git rebase`）
- 将 AI 代码标记为人类写的（此工具仅支持补填 AI 归因）
- 非 git 仓库环境
- git-ai 未安装或 daemon 未运行
