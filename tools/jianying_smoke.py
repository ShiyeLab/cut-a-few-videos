#!/usr/bin/env python3
"""剪映草稿最小验证：生成一个含底图、中央窗视频、标题、字幕、配音五条轨道的测试草稿。

测试素材由 FFmpeg 现场生成，放在草稿目录内；不调用任何外部服务。
运行前先退出剪映；默认备份并更新 Mac 首页索引，再重新打开草稿。
仅生成文件时加 --no-register，不修改首页索引。
草稿生成使用 pyJianYingDraft；文字坐标与 Mac 安装的技术参考为
video-shotcraft 的 references/jianying-export.md；来源与许可见 THIRD_PARTY.md。

用法：
  python3 tools/jianying_smoke.py
  python3 tools/jianying_smoke.py --draft-root "/自定义/剪映草稿目录"
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image
import pyJianYingDraft as draft
from pyJianYingDraft import TrackSpec, TrackType, trange

DEFAULT_ROOT = Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
W, H, FPS, SECONDS = 1080, 1920, 30, 6
WINDOW_Y, WINDOW_H = 380, 1150  # 与默认布局的中央窗一致


def offset_y(center_px: float) -> float:
    """像素纵坐标 → 剪映位移（单位为半个画布高，向上为正）。"""
    return (H / 2 - center_px) / (H / 2)


def make_media(folder: Path) -> dict[str, Path]:
    folder.mkdir()
    media = {"band": folder / "band.png", "clip": folder / "clip.mp4", "voice": folder / "voice.wav"}
    jobs = [
        ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0=0x1d3557:c1=0xf1c27d:d=1", "-frames:v", "1",
         str(media["band"])],
        ["-f", "lavfi", "-i", f"testsrc2=s={W}x{WINDOW_H}:r={FPS}:d={SECONDS}", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(media["clip"])],
        ["-f", "lavfi", "-i", f"sine=f=440:d={SECONDS}", str(media["voice"])],
    ]
    for args in jobs:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)
    return media


def app_running() -> bool:
    if sys.platform != "darwin":
        return False
    processes = subprocess.check_output(["/bin/ps", "-axo", "comm="], text=True)
    return any(f"/{name}.app/Contents/MacOS/" in processes
               for name in ("VideoFusion-macOS", "JianyingPro"))


def read_index(root: Path) -> bytes:
    if app_running():
        raise ValueError("请先退出剪映，再登记草稿；运行中的剪映可能覆盖首页索引")
    path = root / "root_meta_info.json"
    if not path.is_file():
        raise ValueError("未找到 Mac 剪映首页索引；先启动一次剪映，或用 --no-register 仅生成文件")
    original = path.read_bytes()
    index = json.loads(original)
    if not isinstance(index.get("all_draft_store"), list) or not isinstance(index.get("draft_ids"), int):
        raise ValueError("首页索引格式不同，未写入")
    return original


def save_draft(script, folder: Path, draft_id: str, name: str) -> dict:
    """正文、元数据和首页条目共用同一个工程 ID。"""
    now = time.time_ns() // 1000
    content = json.loads(script.dumps())
    content.update(id=draft_id, name=name, create_time=now // 1_000_000,
                   update_time=now // 1_000_000)
    encoded = json.dumps(content, ensure_ascii=False, indent=2)
    for filename in ("draft_content.json", "draft_info.json"):
        (folder / filename).write_text(encoded, encoding="utf-8")
    meta_path = folder / "draft_meta_info.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(draft_id=draft_id, draft_name=name, draft_fold_path=str(folder),
                draft_root_path=str(folder.parent), draft_json_file=str(folder / "draft_info.json"),
                draft_cover=str(folder / "draft_cover.jpg"), tm_duration=content["duration"],
                tm_draft_create=now, tm_draft_modified=now)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def register_draft(root: Path, meta: dict, original: bytes) -> Path:
    path = root / "root_meta_info.json"
    if app_running() or path.read_bytes() != original:
        raise ValueError("剪映或首页索引发生变化，未登记；新草稿文件已保留")
    index = json.loads(original)
    if any(entry.get("draft_id") == meta["draft_id"] for entry in index["all_draft_store"]):
        raise ValueError("首页已存在相同工程 ID，未重复登记")
    index["all_draft_store"].insert(0, meta)
    index["draft_ids"] = len(index["all_draft_store"])
    backup = root / f"root_meta_info.json.before_cut_smoke_{meta['draft_id']}"
    backup.write_bytes(original)
    pending = root / f".cut_smoke_index_{meta['draft_id']}.tmp"
    pending.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(pending, path)
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--draft-root", type=Path, default=DEFAULT_ROOT, help="剪映草稿目录")
    parser.add_argument("--no-register", action="store_true", help="仅生成草稿文件，不登记 Mac 首页")
    args = parser.parse_args()
    args.draft_root = args.draft_root.expanduser().resolve()
    if not args.draft_root.is_dir():
        raise SystemExit(f"找不到剪映草稿目录：{args.draft_root}；请用 --draft-root 指定")

    original = None if args.no_register else read_index(args.draft_root)
    draft_id = str(uuid.uuid4()).upper()
    name = datetime.now().strftime("cut-smoke-%Y%m%d-%H%M%S") + f"-{draft_id[:6]}"
    script = draft.DraftFolder(str(args.draft_root)).create_draft(name, W, H, FPS)
    folder = args.draft_root / name
    media = make_media(folder / "media")

    band, window, title, subs, voice = script.append_tracks([
        TrackSpec(TrackType.video, "底图"), TrackSpec(TrackType.video, "中央窗"),
        TrackSpec(TrackType.text, "标题"), TrackSpec(TrackType.text, "字幕"),
        TrackSpec(TrackType.audio, "配音")])
    whole = trange("0s", f"{SECONDS}s")
    script.add_segment(draft.VideoSegment(str(media["band"]), whole), band)
    script.add_segment(draft.VideoSegment(
        str(media["clip"]), whole,
        clip_settings=draft.ClipSettings(transform_y=offset_y(WINDOW_Y + WINDOW_H / 2))), window)
    script.add_segment(draft.TextSegment(
        "测试标题：可以直接改字", whole,
        style=draft.TextStyle(size=12, bold=True, align=1),
        border=draft.TextBorder(color=(0.1, 0.2, 0.35), width=40),
        shadow=draft.TextShadow(alpha=0.5),
        clip_settings=draft.ClipSettings(transform_y=offset_y(190))), title)
    for start, text in [(0, "第一句字幕"), (SECONDS / 2, "第二句字幕")]:
        script.add_segment(draft.TextSegment(
            text, trange(f"{start}s", f"{SECONDS / 2}s"),
            style=draft.TextStyle(size=8, align=1),
            border=draft.TextBorder(color=(0.1, 0.2, 0.35)),
            clip_settings=draft.ClipSettings(transform_y=offset_y(1425))), subs)
    script.add_segment(draft.AudioSegment(str(media["voice"]), whole), voice)
    with Image.open(media["band"]) as image:
        image = image.convert("RGB")
        image.thumbnail((405, 720))
        image.save(folder / "draft_cover.jpg", quality=85)
    meta = save_draft(script, folder, draft_id, name)
    if original is not None:
        backup = register_draft(args.draft_root, meta, original)
        print(f"已登记 Mac 首页；原索引备份：{backup}")
    print(f"已生成草稿：{folder}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
