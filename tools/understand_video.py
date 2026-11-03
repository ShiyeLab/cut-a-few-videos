#!/usr/bin/env python3
"""调用 MediaKit 理解视频，保存分析与任务号，供主 Agent 选镜。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from check_credentials import load_env


def save(path: Path, value: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def request_for(videos: list[str], prompt: str, level: str) -> dict:
    if not 1 <= len(videos) <= 10 or not prompt.strip():
        raise ValueError("每次提供 1—10 个视频和非空的剪辑目标。")
    paths, local_files = [], []
    for video in videos:
        if "," in video:
            raise ValueError("MediaKit 不接受包含逗号的路径或 URL；请另存为无逗号文件名。")
        if video.startswith(("https://", "http://", "tos://", "vod://")):
            paths.append(video)
        else:
            path = Path(video).resolve(strict=True)
            if not path.is_file():
                raise ValueError("输入必须是视频文件。")
            stat = path.stat()
            paths.append(str(path))
            local_files.append({"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return {"video_urls": paths, "prompt": prompt.strip(), "scene": "editing",
            "level": level, "local_files": local_files}


class CliFailure(ValueError):
    """CLI 以非零退出码给出 success=false 的 JSON；data 为已脱敏的返回内容。"""

    def __init__(self, data: dict):
        error = data.get("error")
        if isinstance(error, dict):
            error = "：".join(str(error[k]) for k in ("code", "message") if error.get(k))
        self.data = data
        self.detail = str(error or "未说明原因")
        super().__init__(f"MediaKit 返回错误：{self.detail}")


def call_cli(cli: str, arguments: list[str], key: str) -> dict:
    env = dict(os.environ)
    # 本项目显式配置优先；缺少配置时不会走到这里，也不读取宿主或其他项目的 Key。
    env["MEDIAKIT_API_KEY"] = key
    try:
        result = subprocess.run([cli, "--cloud", *arguments], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("MediaKit 调用中断；保留任务状态，未自动重发。") from None
    try:
        data = json.loads(result.stdout.replace(key, "[REDACTED]"))
    except (ValueError, TypeError):
        data = None
    if result.returncode:
        # 失败时 CLI 在标准输出给出 success=false 的 JSON；只采用这份结构化结果，不输出原始日志。
        if isinstance(data, dict) and data.get("success") is False:
            raise CliFailure(data)
        raise ValueError("MediaKit 返回错误；检查服务权限与配置。未输出含凭证风险的原始日志。")
    if data is None:
        raise ValueError("MediaKit 未返回有效 JSON；保留状态，不自动重发。")
    if not isinstance(data, dict):
        raise ValueError("MediaKit 返回格式不符合任务协议。")
    return data


def run(request: dict | None, work: Path, env_file: Path, cli: str) -> str:
    receipt_path = work / "receipt.json"
    request_path = work / "request.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if request is not None and json.loads(request_path.read_text(encoding="utf-8")) != request:
            raise ValueError("输入已改变，请使用新的理解目录。")
        if receipt["status"] == "completed":
            if not (work / "analysis.md").is_file() or not (work / "result.json").is_file():
                raise ValueError("已完成任务的结果文件缺失；请恢复文件，不要重新提交。")
            return "completed"
        if receipt["status"] in {"failed", "canceled", "cancelled"}:
            raise ValueError("已有任务失败或取消，请先检查本地回执；未自动重发。")
        if receipt["status"] == "submit_failed":
            raise ValueError("上次提交被服务拒绝，未创建任务；排除原因后使用新的理解目录。")
        if not receipt.get("task_id"):
            raise ValueError("已有提交结果未知，请核对服务端任务；未自动重发。")
    elif request is None:
        raise ValueError("没有已有任务；--poll-only 只查询已保存的真实任务号。")
    else:
        receipt = None

    key = load_env(env_file).get("MEDIAKIT_API_KEY")
    if not key:
        raise ValueError("MEDIAKIT_API_KEY ABSENT；请在指定配置文件填写，不能跳过视频理解。")
    executable = shutil.which(cli)
    if not executable:
        raise ValueError("未找到 mediakit-cli；请按 docs/video-understanding.md 安装。")

    if receipt is None:
        work.mkdir(parents=True, exist_ok=True)
        save(request_path, request)
        receipt = {"provider": "mediakit", "status": "submitting", "task_id": None}
        save(receipt_path, receipt)
        try:
            response = call_cli(executable, ["video", "video-understand-router",
                "--video-urls", ",".join(request["video_urls"]), "--prompt", request["prompt"],
                "--scene", request["scene"], "--level", request["level"]], key)
            task_id = response.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("提交未返回任务号，结果未知；请核对服务端任务。")
        except CliFailure as exc:
            if exc.data.get("task_id"):
                receipt["status"] = "outcome_unknown"
                save(receipt_path, receipt)
                raise
            receipt["status"] = "submit_failed"
            save(receipt_path, receipt)
            raise ValueError(f"MediaKit 拒绝提交：{exc.detail}；未创建任务。") from None
        except ValueError:
            receipt["status"] = "outcome_unknown"
            save(receipt_path, receipt)
            raise
        receipt.update(status="queued", task_id=task_id)
        save(receipt_path, receipt)
        return "queued"

    try:
        response = call_cli(executable, ["shared", "query-task", "--task-id", receipt["task_id"]], key)
    except CliFailure as exc:
        # 带终态的失败是任务结果，照常记录；否则只是本次查询出错，任务保持原状态。
        if exc.data.get("status") not in {"failed", "canceled", "cancelled"}:
            raise ValueError(f"查询原任务出错：{exc.detail}；稍后继续查询。") from None
        response = exc.data
    if response.get("task_id") != receipt["task_id"]:
        raise ValueError("查询返回的任务号不匹配，未采用结果。")
    status = response.get("status")
    if status not in {"queued", "running", "completed", "failed", "canceled", "cancelled"}:
        raise ValueError("查询未返回已知任务状态；稍后继续查询原任务。")
    save(work / "result.json", response)
    if status == "completed":
        contents = response.get("contents")
        if not isinstance(contents, list) or not contents or not all(isinstance(c, str) and c.strip() for c in contents):
            raise ValueError("任务已完成但缺少分析正文；不可据此编排镜头，请核对 result.json。")
        (work / "analysis.md").write_text("\n\n".join(contents) + "\n", encoding="utf-8")
    receipt["status"] = status
    save(receipt_path, receipt)
    if status in {"failed", "canceled", "cancelled"}:
        reason = f"（{CliFailure(response).detail}）" if response.get("error") else ""
        raise ValueError(f"视频理解任务失败或取消{reason}，请检查 result.json；未自动重发。")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", nargs="+")
    parser.add_argument("--prompt", type=Path, help="本条剪辑目标的 UTF-8 文本文件")
    parser.add_argument("--level", choices=["Economy", "Balanced", "Quality"], default="Quality")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env.local"))
    parser.add_argument("--cli", default="mediakit-cli", help="已安装的 MediaKit CLI 可执行文件")
    parser.add_argument("--poll-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.poll_only:
        if args.videos or args.prompt or args.dry_run:
            parser.error("--poll-only 仅需 --work 和服务配置，不与输入或 --dry-run 混用")
        request = None
    else:
        if not args.videos or not args.prompt:
            parser.error("首次提交需要 --videos 和 --prompt")
        request = request_for(args.videos, args.prompt.read_text(encoding="utf-8"), args.level)
    if args.dry_run:
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0
    status = run(request, args.work, args.env, args.cli)
    print(json.dumps({"status": status, "work": str(args.work)}, ensure_ascii=False))
    return 0 if status == "completed" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
