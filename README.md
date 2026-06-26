# git-ai-backfill

为不支持 git-ai hooks 的 Agent 产出的 AI 代码补全归因记录。

## 声明

[git-ai](https://github.com/git-ai-project/git-ai) 的归因机制依赖 Coding Agent 的 hooks 集成——Agent 在编辑文件前后触发 checkpoint，系统才能识别 AI 产出。当使用不支持 hooks 的 Agent（如 ZCode、OpenClaw、Hermes 等）时，即便代码确实由 AI 生成，git-ai 也无法自动记录，导致 AI 产出被漏计为人工代码。

本工具用于解决上述归因缺失问题：对于确实由 AI 生成、但因 Agent 不支持 hooks 而未被记录的代码，可通过本工具补全 git-ai 中的归因信息。

此外，以 AI 代码生成量作为 KPI 存在明显的度量缺陷——该指标依赖 Agent 的 hooks 支持，覆盖范围不完整，且容易被工具层面绕过，不能真实反映研发效率的提升。

_注意：_

- 本工具仅供学习和研究使用，请勿用于任何商业或实际工作中。
- 使用本工具可能会导致 git 仓库历史记录混乱，请务必注意。

## 安装

本工具以 skill 形式分发，自带 Python 脚本，无需单独安装命令。入口：

- `skill/git-ai-backfill/SKILL.md` — skill 定义
- `skill/git-ai-backfill/scripts/git-ai-backfill.py` — Python 3 实现，无第三方依赖

直接运行：

```bash
python3 skill/git-ai-backfill/scripts/git-ai-backfill.py --help
```

## 前置条件

- **git-ai** 已安装并在 PATH 中（[安装指南](https://usegitai.com/)）
- 当前目录是 git 仓库
- git-ai daemon 正在运行

## 参数说明

| 参数        | 类型              | 默认值              | 作用                                                           |
| ----------- | ----------------- | ------------------- | -------------------------------------------------------------- |
| `--mode`    | `{changes, full}` | `changes`           | 操作模式（见下方详细说明）                                     |
| `--files`   | 文件路径列表      | 自动检测脏文件      | 目标文件路径（相对于仓库根目录或绝对路径）                     |
| `--tool`    | 字符串            | `agent`             | AI 代理工具名称，写入归因的 `agent_name`                       |
| `--model`   | 字符串            | `mock-ai`           | AI 模型名称，写入归因的 `model`                                |
| `--session` | 字符串            | 自动生成（时间戳）  | 自定义会话 ID（归因的 `conversation_id`）                      |
| `--dry-run` | 开关              | 关闭                | 只预览会执行的操作，不实际执行                                 |
| `--verbose` | 开关              | 关闭                | 显示 git-ai 命令的详细输出                                     |

> `--tool` / `--model` 的取值优先级：命令行参数 > 环境变量 `GIT_AI_BACKFILL_TOOL` / `GIT_AI_BACKFILL_MODEL` > 默认值。

## 操作模式

### `--mode changes`（标记未提交改动）

将工作区中已修改但未提交的文件变更标记为 AI 产出。

**流程**：

```
1. 检测所有脏文件（git status --porcelain）或使用 --files 指定的文件
2. 对每个文件执行 git add <file>
3. 通过 stdin 把 type=ai_agent 的 JSON 喂给 git-ai checkpoint agent-v1 --hook-input stdin
   （将 HEAD->暂存区的 diff 标为 AI，agent_name/model 来自 --tool/--model）
```

**原理**：`checkpoint agent-v1` 是 git-ai 官方「接入自定义 Agent」的标准入口（见 https://usegitai.com/docs/cli/add-your-agent）。`type=ai_agent` 的 checkpoint 捕获当前已暂存状态，与 HEAD 做 diff，把所有变更归属于 AI。只有实际修改的行被标为 AI，未改变的行保持原归属。

**使用场景**：用尚未被 git-ai 集成 hooks 的 Agent（如 ZCode、OpenClaw 等）改了文件但还没提交，想补登这些修改为 AI 产出。

### `--mode full`（标记整个文件）

将指定文件的全部内容标记为 AI 产出。**仅适用于新文件或与 HEAD 内容不同的文件**（需要有 diff 才能提交）。

**流程**：

```
对每个文件：
1. 将文件内容替换为占位符（"||__AI_LINE_PENDING__||" × 行数）
2. git add <file>
3. git-ai checkpoint agent-v1 --hook-input stdin  （type=human，捕获占位符状态作为人类基线）
4. 恢复文件原始内容
5. git add <file>
6. git-ai checkpoint agent-v1 --hook-input stdin  （type=ai_agent，对比占位符->原始内容的 diff 标为 AI）
```

**原理**：先以 `type=human` 检查点建立占位符基线，再以 `type=ai_agent` 检查点捕获原始内容。两者之间的 diff（占位符->原始内容）全部归属于 AI，实现整文件标记。

**使用场景**：将一个新创建的完整文件标记为 AI 产出。

> **注意**：
>
> - `--mode full` 必须配合 `--files` 指定目标文件
> - 如果文件内容与 HEAD 完全相同，git 会因为无 diff 而拒绝提交

## 使用示例

```bash
# 标记所有未提交的改动为 AI 产出
git-ai-backfill --mode changes

# 标记指定文件的改动为 AI 产出
git-ai-backfill --mode changes --files src/main.rs src/lib.rs

# 将整个文件标记为 AI 产出（新文件）
git-ai-backfill --mode full --files new_module.rs

# 指定 Agent 工具与模型（写入归因元数据）
git-ai-backfill --mode changes --tool zcode --model glm-5.2

# 预览模式（不执行任何操作）
git-ai-backfill --mode changes --dry-run

# 指定自定义会话 ID
git-ai-backfill --mode changes --session my-custom-session-001
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

### `--tool` 和 `--model` 真正写入归因

脚本底层走 git-ai 的 `agent-v1` preset（见 https://usegitai.com/docs/cli/add-your-agent），这是 git-ai 官方「接入自定义 Agent」的标准入口。`--tool` 写入归因的 `agent_name`、`--model` 写入归因的 `model`，两者都会真实写入 attribution 元数据（见 git-ai 源码 `src/commands/checkpoint_agent/presets/agent_v1.rs`，对应 `tool: agent_name` / `model`）。

### 归属边界效应

由于 git diff 的 hunk 边界效应，某些行可能被意外归属到相邻的 hunk。例如：

- 文件末尾新增的 AI 行可能将原最后一行也归为 AI
- 连续编辑区域中未修改的行可能被拉入 AI hunk

这是 git-ai 基于 diff hunk 进行归属的固有行为，非脚本 bug。

## 原理

git-ai 区分 AI 和人类代码的核心机制是 **检查点（Checkpoint）**。本工具通过 `agent-v1` preset 模拟一个自定义 Agent 的编辑流程：

1. `full` 模式编辑前先发一个 `type=human` 的 checkpoint，捕获占位符"前"状态作为人类基线
2. 发一个 `type=ai_agent` 的 checkpoint，捕获"后"状态（`agent_name`/`model` 即 `--tool`/`--model`）
3. 系统对比前后差异，AI 类型的 checkpoint 触发 `force_split` 策略，将所有变更归属于 AI

`changes` 模式省略第 1 步，直接对 HEAD → 工作区的 diff 做一次 AI checkpoint。

## License

MIT
