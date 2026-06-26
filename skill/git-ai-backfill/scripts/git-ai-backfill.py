#!/usr/bin/env python3
"""
git-ai-backfill.py — 为 git-ai 官方支持列表之外的 Coding Agent 补登记 AI 归因

适用场景：使用了 git-ai 尚未集成 hooks 的 Agent（如 ZCode、OpenClaw、Hermes 等）
产出的代码，由于这些 Agent 不会触发 checkpoint，git-ai 无法自动记录其归因。
本工具手动补填这些缺失的 checkpoint，使代码在 git-ai 系统中被正确识别为 AI 产出。

原理（基于 git-ai 的 agent-v1 preset，详见
https://usegitai.com/docs/cli/add-your-agent）：

  changes 模式：对脏文件执行 `git-ai checkpoint agent-v1`，
    传入 type=ai_agent 的 hook_input，把 HEAD → 工作区的 diff 标为 AI 产出。
    tool/model 由 --tool/--model（或对应环境变量）控制，真正写入归因元数据。

  full 模式：先把文件替换为占位符并做 type=human 的 checkpoint（人类基线），
    再恢复原始内容并做 type=ai_agent 的 checkpoint，使全部内容被标为 AI。

两种模式执行完成后，均需手动运行 `git commit` 使归因生效。

前置条件：
  - git-ai 已安装并在 PATH 中
  - 当前目录是 git 仓库
  - git-ai daemon 正在运行
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple


def run_cmd(
    cmd: List[str],
    dry_run: bool = False,
    capture: bool = True,
    stdin_data: Optional[str] = None,
    verbose: bool = False,
) -> Optional[str]:
    """执行命令。dry_run 时只打印不执行。返回 stdout（capture 时）或空串。"""
    if dry_run:
        suffix = f" <<'EOF'\n{stdin_data}\nEOF" if stdin_data is not None else ""
        print(f"  [DRY RUN] {' '.join(cmd)}{suffix}")
        return None
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=30,
            input=stdin_data,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            if capture and stderr:
                print(f"  [WARN] command stderr: {stderr}", file=sys.stderr)
            return None
        if verbose and capture and result.stderr:
            print(f"  [VERBOSE] {result.stderr.strip()}", file=sys.stderr)
        return result.stdout.strip() if capture else ""
    except FileNotFoundError:
        print(f"  [ERROR] command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] command timed out: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(1)


def check_git_ai_installed() -> bool:
    result = run_cmd(["which", "git-ai"])
    return result is not None and result.strip() != ""


def check_git_repo() -> bool:
    result = run_cmd(["git", "rev-parse", "--is-inside-work-tree"])
    return result is not None and result.strip() == "true"


def get_repo_root() -> Optional[str]:
    return run_cmd(["git", "rev-parse", "--show-toplevel"])


def get_dirty_files(repo_root: str) -> List[str]:
    """自动检测已修改、已暂存的已追踪文件；跳过已删除(D)和未追踪(??)。"""
    result = run_cmd(["git", "-c", "core.quotePath=false", "status", "--porcelain"])
    if not result:
        return []
    files = []
    for line in result.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        filepath = parts[1].strip().strip('"')
        if status.startswith("??"):
            continue
        if status.startswith("D "):
            continue
        abs_path = os.path.join(repo_root, filepath)
        if os.path.isfile(abs_path):
            files.append(abs_path)
    return files


def resolve_file_paths(files: List[str], repo_root: str) -> List[str]:
    resolved = []
    for f in files:
        p = Path(f)
        if p.is_absolute():
            resolved.append(str(p))
        else:
            abs_path = os.path.join(repo_root, f)
            if os.path.isfile(abs_path):
                resolved.append(abs_path)
            else:
                print(f"  [WARN] file not found: {f} (resolved to {abs_path})", file=sys.stderr)
    return resolved


def get_file_content(filepath: str) -> Optional[str]:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (IOError, OSError) as e:
        print(f"  [WARN] cannot read {filepath}: {e}", file=sys.stderr)
        return None


def write_file_content(filepath: str, content: str) -> bool:
    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except (IOError, OSError) as e:
        print(f"  [ERROR] cannot write {filepath}: {e}", file=sys.stderr)
        return False


PLACEHOLDER = "||__AI_LINE_PENDING__||\n"


def make_ai_hook_input(
    repo_working_dir: str,
    files: List[str],
    tool: str,
    model: str,
    conversation_id: str,
) -> str:
    """生成 agent-v1 preset 的 type=ai_agent hook_input JSON。

    agent_name → 写入归因的 tool；model → 写入归因的 model。
    见上游 src/commands/checkpoint_agent/presets/agent_v1.rs。
    """
    return json.dumps({
        "type": "ai_agent",
        "repo_working_dir": repo_working_dir,
        "edited_filepaths": files,
        "agent_name": tool,
        "model": model,
        "conversation_id": conversation_id,
    }, ensure_ascii=False)


def make_human_hook_input(repo_working_dir: str, files: List[str]) -> str:
    """生成 agent-v1 preset 的 type=human hook_input JSON（人类基线）。"""
    return json.dumps({
        "type": "human",
        "repo_working_dir": repo_working_dir,
        "will_edit_filepaths": files,
    }, ensure_ascii=False)


def checkpoint_agent_v1(
    hook_input: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """通过 stdin 把 hook_input 喂给 `git-ai checkpoint agent-v1`。

    用 --hook-input stdin 传递，避免命令行参数对 JSON 的转义问题。
    文件路径已在 hook_input 中给出，无需作为尾部参数（agent-v1 不像
    mock_ai 那样从尾部参数合成 hook_input）。
    """
    run_cmd(
        ["git-ai", "checkpoint", "agent-v1", "--hook-input", "stdin"],
        dry_run=dry_run,
        stdin_data=hook_input,
        verbose=verbose,
    )


def make_conversation_id(session: Optional[str]) -> str:
    if session:
        return session
    return f"backfill-{int(time.time())}-{os.getpid()}"


def do_mark_changes(
    files: List[str],
    repo_root: str,
    tool: str,
    model: str,
    session: Optional[str],
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    print("\n[Mode: changes] Marking uncommitted changes as AI-authored...")
    print(f"  Files ({len(files)}):")
    for f in files:
        print(f"    - {os.path.relpath(f, repo_root)}")

    conversation_id = make_conversation_id(session)
    print(f"  Agent: {tool} / {model} / conversation={conversation_id}")

    print("\n  Step 1/1: AI checkpoint (diff from HEAD → working tree marked as AI)...")
    for f in files:
        if dry_run:
            print(f"  [DRY RUN] git add {os.path.relpath(f, repo_root)}")
        else:
            run_cmd(["git", "add", f])

    # 一次性把所有文件放进同一个 hook_input（agent-v1 支持多文件）。
    hook_input = make_ai_hook_input(repo_root, files, tool, model, conversation_id)
    checkpoint_agent_v1(hook_input, dry_run=dry_run, verbose=verbose)

    print("\n  Done. The staged diff from HEAD is now attributed to AI.")
    print("  Run: git commit -m \"your message\"")


def do_mark_full(
    files: List[str],
    repo_root: str,
    tool: str,
    model: str,
    session: Optional[str],
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    print("\n[Mode: full] Marking entire files as AI-authored...")
    print(f"  Files ({len(files)}):")
    for f in files:
        print(f"    - {os.path.relpath(f, repo_root)}")

    conversation_id = make_conversation_id(session)
    print(f"  Agent: {tool} / {model} / conversation={conversation_id}")

    for f in files:
        content = get_file_content(f) if not dry_run else "dummy"
        if content is None:
            continue

        lines = content.split("\n")
        has_real_content = any(line.strip() for line in lines)
        if not has_real_content:
            print(f"  [SKIP] {os.path.relpath(f, repo_root)} — empty file")
            continue

        placeholder_content = PLACEHOLDER * len(
            [l for l in lines if l.strip() or l == lines[-1]]
        )
        if not placeholder_content.endswith("\n") and content.endswith("\n"):
            placeholder_content += "\n"

        rel = os.path.relpath(f, repo_root)
        if not dry_run:
            print(f"\n  Processing: {rel}")
            print("    Step 1/4: Write placeholder content...")
            if not write_file_content(f, placeholder_content):
                continue
            print("    Step 2/4: Stage + Pre-edit checkpoint (human baseline)...")
            run_cmd(["git", "add", f])
            human_input = make_human_hook_input(repo_root, [f])
            checkpoint_agent_v1(human_input, dry_run=False, verbose=verbose)

            print("    Step 3/4: Restore original content + stage...")
            write_file_content(f, content)
            run_cmd(["git", "add", f])

            print("    Step 4/4: Post-edit checkpoint (AI attribution)...")
            ai_input = make_ai_hook_input(repo_root, [f], tool, model, conversation_id)
            checkpoint_agent_v1(ai_input, dry_run=False, verbose=verbose)
        else:
            print(f"\n  [DRY RUN] Processing: {rel}")
            print("    Step 1/4: [DRY RUN] Write placeholder content")
            print("    Step 2/4: [DRY RUN] git add + checkpoint agent-v1 (type=human)")
            print("    Step 3/4: [DRY RUN] Restore original + git add")
            print("    Step 4/4: [DRY RUN] checkpoint agent-v1 (type=ai_agent)")
            print(f"             ai_input={make_ai_hook_input(repo_root, [f], tool, model, conversation_id)}")

    print("\n  Done. Run: git commit -m \"your message\"")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill git-ai attribution for AI code from agents git-ai doesn't hook into",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --mode changes                              Mark all uncommitted changes as AI
  %(prog)s --mode changes --files src/main.rs           Mark specific file changes as AI
  %(prog)s --mode full --files README.md                Mark entire file as AI
  %(prog)s --mode changes --dry-run                     Preview operations without executing
  %(prog)s --mode changes --tool zcode --model glm-5.2  Custom agent tool/model
""",
    )

    parser.add_argument(
        "--mode",
        choices=["changes", "full"],
        default="changes",
        help=(
            "Operation mode:\n"
            "  changes — Mark uncommitted file changes as AI (Pre/Post checkpoint on current diff)\n"
            "  full    — Mark entire file(s) as AI (replace→checkpoint→restore→checkpoint)"
        ),
    )

    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help=(
            "Target file paths (relative to repo root or absolute). "
            "If omitted in 'changes' mode, auto-detects all dirty tracked files."
        ),
    )

    parser.add_argument(
        "--tool",
        default=os.environ.get("GIT_AI_BACKFILL_TOOL", "agent"),
        help=(
            "AI agent tool name written into attribution (agent_name in agent-v1). "
            "Falls back to GIT_AI_BACKFILL_TOOL env var, then 'agent'."
        ),
    )

    parser.add_argument(
        "--model",
        default=os.environ.get("GIT_AI_BACKFILL_MODEL", "mock-ai"),
        help=(
            "AI model name written into attribution. "
            "Falls back to GIT_AI_BACKFILL_MODEL env var, then 'mock-ai'."
        ),
    )

    parser.add_argument(
        "--session",
        default=None,
        help=(
            "Custom conversation_id for the AI attribution. "
            "If not set, a timestamp-based ID is generated automatically."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing any commands.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output from git-ai commands.",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("GIT AI BACKFILL Attribution Tool")
    print("=" * 60)
    print(f"  Mode:   {args.mode}")
    print(f"  Tool:   {args.tool}")
    print(f"  Model:  {args.model}")
    if args.session:
        print(f"  Session: {args.session}")
    if args.dry_run:
        print(f"  DRY RUN: No commands will be executed")
    print()

    if not check_git_ai_installed():
        print("[ERROR] git-ai is not installed or not in PATH.", file=sys.stderr)
        print("        Install from: https://usegitai.com/", file=sys.stderr)
        sys.exit(1)

    if not check_git_repo():
        print("[ERROR] Not inside a git repository.", file=sys.stderr)
        sys.exit(1)

    repo_root = get_repo_root()
    if not repo_root:
        print("[ERROR] Cannot determine git repo root.", file=sys.stderr)
        sys.exit(1)

    if args.files:
        files = resolve_file_paths(args.files, repo_root)
        if not files:
            print("[ERROR] No valid files specified.", file=sys.stderr)
            sys.exit(1)
    elif args.mode == "changes":
        files = get_dirty_files(repo_root)
        if not files:
            print("[INFO] No uncommitted changes found. Nothing to do.")
            sys.exit(0)
    elif args.mode == "full":
        print("[ERROR] --files is required when using --mode full.", file=sys.stderr)
        sys.exit(1)
    else:
        files = []

    if args.mode == "changes":
        do_mark_changes(
            files, repo_root, args.tool, args.model, args.session,
            dry_run=args.dry_run, verbose=args.verbose,
        )
    elif args.mode == "full":
        do_mark_full(
            files, repo_root, args.tool, args.model, args.session,
            dry_run=args.dry_run, verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
