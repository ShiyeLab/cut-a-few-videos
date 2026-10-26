#!/usr/bin/env python3
"""MiniMax H3 文生视频：按镜头需求生成"过渡空镜"，保存请求、任务号、结果与抽帧。

为什么单独做这一层：
  本项目要的是"过程空镜"——没有产品、没有可读文字的环境镜头，用来接住口播里的动作与情绪。
  素材本身（封面/内页/翻页/抄写）仍必须用真实书本，AI 只补情绪与环境，不冒充书。

约定：
  - Key 来自指定配置文件的 MINIMAX_API_KEY（只报告 PRESENT/ABSENT，不打印、不落盘）；
  - 中国站为 https://api.minimaxi.com，须使用与该站点匹配的 Key；
  - 提交前先写回执；已有成功结果直接复用；失败不自动重发；
  - 结果下载到 projects/ai/<slug>/，同时抽首/中/尾三帧供人眼核对。

用法：
  python3 tools/minimax_video.py --spec templates/ai-video.json
  python3 tools/minimax_video.py --spec ... --only window,tea
  python3 tools/minimax_video.py --spec ... --poll-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.minimaxi.com"
MODEL = "MiniMax-H3"
from check_credentials import load_env


def load_key(path: str) -> str:
    key = load_env(Path(path)).get("MINIMAX_API_KEY")
    if not key:
        raise SystemExit("MINIMAX_API_KEY ABSENT")
    return key


def call(method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500]}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def ffmpeg(args: list[str]) -> None:
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ffmpeg 失败: {' '.join(args)}\n{p.stderr[-800:]}")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.mp4")
    with urllib.request.urlopen(url, timeout=180) as r, tmp.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def submit(item: dict, key: str, folder: Path) -> dict:
    """提交前写回执；返回回执状态。"""
    receipt_path = folder / "receipt.json"
    body = {
        "model": MODEL,
        "content": [{"type": "text", "text": item["prompt"]}],
        "resolution": item.get("resolution", "768P"),
        "duration": int(item.get("duration", 6)),
        "ratio": item.get("ratio", "1:1"),
    }
    if receipt_path.exists():
        state = json.loads(receipt_path.read_text())
        if state.get("request") != body:
            raise SystemExit(f"{folder.name}: 请求已改变，请换 slug 或先确认旧任务")
        return state
    state = {"slug": folder.name, "purpose": item.get("purpose", ""), "request": body,
             "status": "submitting", "task_id": None}
    save(receipt_path, state)
    code, resp = call("POST", "/v2/video_generation", key, body)
    if code != 200 or "task_id" not in resp:
        state.update(status="submit_failed", http_status=code, response=resp)
        save(receipt_path, state)
        raise SystemExit(f"{folder.name}: 提交失败 HTTP {code}")
    state.update(status="queued", task_id=str(resp["task_id"]))
    save(receipt_path, state)
    print(f"  {folder.name}: 已提交 task_id={state['task_id']}")
    return state


def poll(folder: Path, key: str, timeout_s: int = 900) -> dict:
    receipt_path = folder / "receipt.json"
    state = json.loads(receipt_path.read_text())
    if state.get("status") in ("succeeded", "failed", "cancelled"):
        return state
    if not state.get("task_id"):
        return state
    started = time.time()
    while time.time() - started < timeout_s:
        try:
            code, resp = call("GET", f"/v2/query/video_generation/{state['task_id']}", key)
        except Exception as exc:  # 已受理的任务不因一次断线丢掉；继续查询同一个 id
            print(f"  {folder.name}: 查询中断（{type(exc).__name__}），稍后重试同一任务")
            time.sleep(10)
            continue
        task = (resp or {}).get("task", {})
        status = task.get("status")
        if code == 200 and status:
            state["status"] = status
            state["last_response"] = {"model": task.get("model"), "duration": task.get("duration"),
                                      "resolution": task.get("resolution"), "ratio": task.get("ratio"),
                                      "usage": task.get("usage")}
            if status in ("succeeded", "failed", "cancelled"):
                save(receipt_path, state)
                return state
        time.sleep(8)
    state.update(status="timeout")
    save(receipt_path, state)
    return state


def fetch(folder: Path, key: str) -> None:
    receipt_path = folder / "receipt.json"
    state = json.loads(receipt_path.read_text())
    code, resp = call("GET", f"/v2/query/video_generation/{state['task_id']}", key)
    url = ((resp or {}).get("task", {}).get("content") or {}).get("url")
    if not url:
        raise SystemExit(f"{folder.name}: 查询结果里没有视频地址")
    target = folder / "clip.mp4"
    download(url, target)
    dur = probe_duration(target)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=width,height,r_frame_rate,codec_name", "-of", "json", str(target)],
                           capture_output=True, text=True).stdout
    ffmpeg(["-i", str(target), "-f", "null", "-"])
    for frac, name in ((0.1, "f1"), (0.5, "f2"), (0.9, "f3")):
        ffmpeg(["-ss", f"{dur * frac:.2f}", "-i", str(target), "-frames:v", "1",
                "-vf", "scale=480:-1", str(folder / f"{name}.jpg")])
    state.update(status="downloaded", file=str(target.relative_to(ROOT)),
                 duration=round(dur, 3), streams=json.loads(probe)["streams"][0])
    save(receipt_path, state)
    print(f"  {folder.name}: 已下载 {dur:.1f}s → {target.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--only", default=None, help="逗号分隔的 slug")
    ap.add_argument("--poll-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--out", default="projects/ai", help="仓库内输出目录")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    items = [i for i in spec["items"] if not only or i["slug"] in only]
    key = load_key(args.env)
    print(f"MINIMAX_API_KEY PRESENT；本次 {len(items)} 个镜头")

    # 第一阶段：把还没提交的一次性全部提交，避免排队等待串行叠加
    pending = []
    for item in items:
        folder = ROOT / args.out / item["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        save(folder / "prompt.json", item)
        receipt = folder / "receipt.json"
        state = json.loads(receipt.read_text()) if receipt.exists() else None
        if state and state.get("status") == "downloaded":
            print(f"  {item['slug']}: 已有结果，跳过")
            continue
        if state and state.get("status") == "submit_failed":
            raise SystemExit(f"{item['slug']}: 上次提交失败，先人工确认，不自动重发")
        if state is None and not args.poll_only:
            state = submit(item, key, folder)
        if state and state.get("task_id"):
            pending.append((item["slug"], folder))

    # 第二阶段：逐个查状态并下载
    for slug, folder in pending:
        state = poll(folder, key, args.timeout)
        print(f"  {slug}: {state.get('status')}")
        if state.get("status") == "succeeded":
            fetch(folder, key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
