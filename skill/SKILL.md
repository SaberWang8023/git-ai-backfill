---
name: git-ai-backfill
description: 为不支持 git-ai hooks 的 Agent（如 OpenClaw、Hermes 等）产出的 AI 代码补全归因记录。通过 git-ai 的 checkpoint 机制将漏记的 AI 代码补填到归属系统中。
---

# git-ai-backfill

通过 `git-ai-backfill` CLI 工具，利用 git-ai 的检查点机制，为因 Agent 不支持 hooks 而漏记的 AI 代码补全归因信息。

## 前置条件

- git-ai 已安装并在 PATH 中
- 当前目录是 git 仓库
- git-ai daemon 正在运行

如未安装 git-ai，告知用户前往 https://github.com/anomalyco/git-ai 安装。

## 使用时机

当用户表达以下意图时使用此 skill：

- "把这些改动补填为 AI 产出的归因"
- "这段代码是 AI 写的但没有被记录"
- "补全 git-ai 归因"
- "backfill ai attribution"
- "这个 Agent 不支持 hooks，帮我补填归因"

## 工作流

### 第 1 步：确认用户意图和范围

在执行任何操作前，必须向用户确认：

1. **目标文件**：哪些文件需要标记？
2. **操作模式**：
   - `changes`（默认）：只标记未提交的改动
   - `full`：标记整个文件（仅适用于新文件或与 HEAD 不同的文件）

如果用户未明确指定文件，询问是否要标记所有未提交的改动。

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

## 操作模式详解

### changes 模式

标记工作区中已修改但未提交的文件变更。

- 只有**实际修改的行**被标为 AI
- 未改变的行保持原归属
- 不需要指定 `--files`（自动检测脏文件）

### full 模式

标记文件的**全部内容**为 AI。

- **必须**指定 `--files`
- 仅适用于新文件或与 HEAD 不同的文件（需要有 diff 才能提交）
- 通过占位符技术实现：写入占位符 → human checkpoint → 恢复原始内容 → AI checkpoint

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mode` | `changes` | 操作模式：`changes` 或 `full` |
| `--files` | 自动检测 | 目标文件路径 |
| `--tool` | `claude` | AI 工具名（信息性，不影响实际归属） |
| `--model` | `claude-sonnet-4.6` | AI 模型名（信息性） |
| `--session` | 自动生成 | 自定义会话 ID（信息性） |
| `--dry-run` | 关闭 | 预览模式 |

## 注意事项

1. **tool 和 model 参数是信息性的**：内部使用 `mock_ai` preset，实际归属中 `tool` 固定为 `mock_ai`，`model` 固定为 `unknown`
2. **归属边界效应**：git diff 的 hunk 边界可能导致相邻未修改行被意外归为 AI
3. **不自动提交**：脚本只创建 checkpoint，用户需手动 commit
4. **full 模式的限制**：文件内容与 HEAD 完全相同时无法使用（无 diff 无法提交）

## 示例交互

```
用户: 把 src/main.rs 的改动标记为 AI 写的

AI: 我来帮你标记。先预览一下操作：
    [执行] git-ai-backfill --mode changes --files src/main.rs --dry-run
    [展示 dry-run 输出]
    确认执行吗？

用户: 确认

AI: [执行] git-ai-backfill --mode changes --files src/main.rs
    标记完成。请执行以下命令提交：
    git commit -m "your message"
```

## 不适用场景

- 用户想修改已有提交的归属（需要 `git commit --amend` 或 `git rebase`）
- 用户想将 AI 代码标记为人类写的（此工具只支持反向操作）
- 非 git 仓库环境
- git-ai 未安装
