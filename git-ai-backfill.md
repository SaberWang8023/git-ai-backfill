# git-ai-backfill-attribution.py 参数说明文档

## 概述

`git-ai-backfill-attribution.py` 是一个 Python 脚本，用于将人类编写的代码在 git-ai 系统中标记为 AI 产出。

**原理**：利用 git-ai 的检查点机制。检查点（checkpoint）是 git-ai 区分 AI 和人类代码的核心方式——系统对比检查点时的文件状态与上一次检查点（或 HEAD）的差异，根据检查点类型（`human` vs `mock_ai`）决定归属。

## 前置条件

- git-ai 已安装并在 PATH 中
- 当前目录是 git 仓库
- git-ai daemon 正在运行

## 参数说明

| 参数 | 类型 | 默认值 | 作用 |
|------|------|--------|------|
| `--mode` | `{changes, full}` | `changes` | 操作模式（见下方详细说明） |
| `--files` | 文件路径列表 | 自动检测脏文件 | 目标文件路径（相对于仓库根目录或绝对路径） |
| `--tool` | 字符串 | `claude` | AI 代理工具名称（信息性，实际 agent_id.tool 固定为 `mock_ai`） |
| `--model` | 字符串 | `claude-sonnet-4.6` | AI 模型名称（信息性，实际 agent_id.model 固定为 `unknown`） |
| `--session` | 字符串 | 自动生成（时间戳） | 自定义会话 ID（信息性） |
| `--dry-run` | 开关 | 关闭 | 只预览会执行的操作，不实际执行 |
| `--verbose` | 开关 | 关闭 | 显示 git-ai 命令的详细输出 |

## 操作模式

### `--mode changes`（标记未提交改动）

将工作区中已修改但未提交的文件变更标记为 AI 产出。

**流程**：

```
1. 检测所有脏文件（git status --porcelain）或使用 --files 指定的文件
2. 对每个文件执行 git add <file>                   （暂存变更）
3. 对每个文件执行 git-ai checkpoint mock_ai <file>  （将 HEAD→工作区的 diff 标为 AI）
```

**原理**：`checkpoint mock_ai` 捕获当前已暂存的文件状态，与 HEAD（或上一次检查点）做 diff，由于 `is_ai_checkpoint=true`，所有变更被归属于 AI。只有实际修改的行被标为 AI，未改变的行保持原归属。

**使用场景**：人类已经修改了文件但尚未提交，想让这些修改显示为 AI 产出。

### `--mode full`（标记整个文件）

将指定文件的全部内容标记为 AI 产出。**仅适用于新文件或与 HEAD 内容不同的文件**（需要有 diff 才能提交）。

**流程**：

```
对每个文件：
1. 将文件内容替换为占位符（"||__AI LINE__ PENDING__||" × 行数）
2. git add <file>
3. 执行 git-ai checkpoint mock_known_human <file>  （捕获占位符状态作为基线）
4. 恢复文件原始内容
5. git add <file>
6. 执行 git-ai checkpoint mock_ai <file>  （对比占位符→原始内容的 diff 标为 AI）
```

**原理**：先以 `mock_known_human` 检查点建立占位符基线，再以 `mock_ai` 检查点捕获原始内容。两者之间的 diff（占位符→原始内容）全部归属于 AI，实现整文件标记。

**使用场景**：将一个新创建的完整文件标记为 AI 产出。

> **注意**：
> - `--mode full` 必须配合 `--files` 指定目标文件
> - 如果文件内容与 HEAD 完全相同，git 会因为无 diff 而拒绝提交。此模式适用于新文件或内容有变更的文件

## 使用示例

```bash
# 标记所有未提交的改动为 AI 产出
python git-ai-backfill-attribution.py --mode changes

# 标记指定文件的改动为 AI 产出
python git-ai-backfill-attribution.py --mode changes --files src/main.rs src/lib.rs

# 将整个文件标记为 AI 产出
python git-ai-backfill-attribution.py --mode full --files README.md

# 自定义模型信息
python git-ai-backfill-attribution.py --mode changes --tool claude --model claude-sonnet-4-20250514

# 预览模式（不执行任何操作）
python git-ai-backfill-attribution.py --mode changes --dry-run

# 指定自定义会话 ID
python git-ai-backfill-attribution.py --mode changes --session my-custom-session-001
```

## 执行后的操作

脚本执行完成后，需要手动 commit 使 attribution 生效：

```bash
git commit -m "your commit message"
```

提交时 git-ai 的 post-commit hook 会自动将 AI 归因信息写入 `refs/notes/ai`。

验证归因结果：

```bash
git-ai blame <file>        # 查看行级归属
git-ai stats HEAD --json   # 查看提交统计
```

## 重要说明

### `--tool` 和 `--model` 的局限性

脚本内部使用 `mock_ai` preset（`git-ai checkpoint mock_ai`），其源码中硬编码了：

```rust
// src/commands/checkpoint_agent/presets/mock_ai.rs
AgentId {
    tool: "mock_ai".to_string(),   // 固定值
    id: mock_agent_id,             // 基于时间戳自动生成
    model: "unknown".to_string(),  // 固定值
}
```

因此 `--tool` 和 `--model` 参数目前仅为信息性参数，不会影响实际的 attribution 元数据。

**如需真正自定义 agent_id**，有以下方案：

1. 修改 `mock_ai.rs` 源码，使其从 hook_input JSON 中读取 `tool` 和 `model` 字段
2. 使用 `claude` 等真实 preset 配合 `--hook-input` 传入自定义 JSON
3. 创建新的 preset（如 `forced_ai`）支持自定义参数

### 归属边界效应

由于 git diff 的 hunk 边界效应，某些行可能被意外归属到相邻的 hunk。例如：

- 文件末尾新增的 AI 行可能将原最后一行也归为 AI
- 连续编辑区域中未修改的行可能被拉入 AI hunk

这是 git-ai 基于 diff hunk 进行归属的固有行为，非脚本 bug。
