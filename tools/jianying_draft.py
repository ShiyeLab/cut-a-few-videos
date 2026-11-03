#!/usr/bin/env python3
"""把一次合成的产物转成可编辑的剪映草稿：中央窗视频、底图、标题、底部文字、字幕、配音各自成轨。

读取 build_video.py 输出目录里的 compose_args.json、layout.json、shots.json、subs.json 与
layout_report.json，和 MP4 共用同一份时间轴。草稿只是供修改的近似版：镜头之间硬切，
不带运镜与转场，过场和配乐由用户在剪映里加；文字用剪映默认字体，用户可自行替换。

媒体复制进草稿目录（Mac 剪映沙盒只能访问自己目录下的文件）。build_video.py 合成后自动调用；
剪映没开时备份并登记首页索引，开着时只生成文件，退出剪映后用 --register 补登记。
技术参考：pyJianYingDraft；video-shotcraft 的 references/jianying-export.md（字号与 Mac 安装）。

用法：
  python3 tools/jianying_draft.py --work projects/my-video/out/01-v1   # 给已有输出目录补导出
  python3 tools/jianying_draft.py --register                           # 登记未登记的草稿
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from PIL import Image
import pyJianYingDraft as draft
from pyJianYingDraft import TrackSpec, TrackType

import layout as L

if sys.platform == "win32":
    DEFAULT_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / \
        "JianyingPro/User Data/Projects/com.lveditor.draft"
else:
    DEFAULT_ROOT = Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
PX_PER_SIZE = 10.8  # 像素字号 ÷ 10.8 ≈ 剪映字号；近似值，用户在剪映里可再调


def app_running() -> bool:
    if sys.platform == "win32":
        processes = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, errors="replace")
        return '"jianyingpro.exe"' in processes.lower()
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
        raise ValueError("未找到剪映首页索引；先启动一次剪映，或用 --no-register 仅生成文件")
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


def register_drafts(root: Path, metas: list[dict], original: bytes) -> Path:
    """一次写入若干条首页条目；写入前备份原索引，剪映运行或索引已变时不写。"""
    path = root / "root_meta_info.json"
    if app_running() or path.read_bytes() != original:
        raise ValueError("剪映或首页索引发生变化，未登记；新草稿文件已保留")
    index = json.loads(original)
    known = {entry.get("draft_id") for entry in index["all_draft_store"]}
    if any(meta["draft_id"] in known for meta in metas):
        raise ValueError("首页已存在相同工程 ID，未重复登记")
    index["all_draft_store"][:0] = metas
    index["draft_ids"] = len(index["all_draft_store"])
    backup = root / f"root_meta_info.json.before_cut_draft_{metas[0]['draft_id']}"
    backup.write_bytes(original)
    pending = root / f".cut_draft_index_{metas[0]['draft_id']}.tmp"
    pending.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(pending, path)
    return backup


def register_draft(root: Path, meta: dict, original: bytes) -> Path:
    return register_drafts(root, [meta], original)


PENDING = ".cut_drafts_pending.json"  # 已生成、待退出剪映后登记的草稿文件夹名


def mark_pending(root: Path, name: str) -> None:
    path = root / PENDING
    names = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    path.write_text(json.dumps([*names, name], ensure_ascii=False), encoding="utf-8")


def register_pending(root: Path) -> list[str]:
    """登记所有待登记的草稿，返回登记的草稿名；已删除或已在首页的条目直接移出清单。"""
    path = root / PENDING
    names = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    original = read_index(root)
    known = {entry.get("draft_id") for entry in json.loads(original)["all_draft_store"]}
    metas = []
    for name in names:
        meta_path = root / name / "draft_meta_info.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["draft_id"] not in known:
                metas.append(meta)
    if metas:
        register_drafts(root, metas, original)
    path.unlink(missing_ok=True)
    return [meta["draft_name"] for meta in metas]


def write_cover(image_path: Path, folder: Path) -> None:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((405, 720))
        image.save(folder / "draft_cover.jpg", quality=85)


def span(start: float, end: float) -> draft.Timerange:
    """按微秒取整后再求时长，相邻片段首尾严格相接。"""
    a, b = round(start * draft.SEC), round(end * draft.SEC)
    return draft.Timerange(a, b - a)


def rgb(value: str) -> tuple[float, float, float]:
    r, g, b, _ = L.hex_rgba(value)
    return r / 255, g / 255, b / 255


def place(material_w: int, material_h: int, canvas: tuple[int, int], win: dict, fit: str,
          focus_y: float) -> draft.ClipSettings:
    """让素材按 cover/contain 落在中央窗里。剪映默认把素材等比放进整个画布，scale 相对该尺寸。

    cover 时超出中央窗的部分由上层底图遮住，与成片的裁切一致；focus_y 决定竖向取景。
    blur 在草稿里按 contain 处理，不做虚化背景。
    """
    cw, ch = canvas
    base = min(cw / material_w, ch / material_h)
    pick = max if fit == "cover" else min
    scale = pick(win["w"] / material_w, win["h"] / material_h)
    overflow = material_h * scale - win["h"]
    center_y = win["y"] + win["h"] / 2 + (0.5 - focus_y) * max(overflow, 0)
    center_x = win["x"] + win["w"] / 2
    return draft.ClipSettings(scale_x=scale / base, scale_y=scale / base,
                              transform_x=(center_x - cw / 2) / (cw / 2),
                              transform_y=(ch / 2 - center_y) / (ch / 2))


def text_segment(text: str, start: float, end: float, spec: dict, size_px: int,
                 center_y: float, canvas_h: int) -> draft.TextSegment:
    shadow = spec.get("shadow")
    return draft.TextSegment(
        text, span(start, end),
        style=draft.TextStyle(size=round(size_px / PX_PER_SIZE, 2), align=1, color=rgb(spec["color"])),
        border=draft.TextBorder(color=rgb(spec["stroke_color"]), width=min(100.0, 6.0 * spec["stroke_width"]))
        if spec.get("stroke_width") else None,
        shadow=draft.TextShadow(alpha=float(shadow.get("opacity", 0.5)), color=rgb(shadow.get("color", "#000000")))
        if shadow else None,
        clip_settings=draft.ClipSettings(transform_y=(canvas_h / 2 - center_y) / (canvas_h / 2)))


def block_center(lines: list[dict]) -> float:
    top = min(line["y"] for line in lines)
    bottom = max(line["y"] + line["h"] for line in lines)
    return (top + bottom) / 2


def build(work: Path, root: Path, name: str, draft_id: str) -> Path:
    args = json.loads((work / "compose_args.json").read_text(encoding="utf-8"))
    cfg = json.loads((work / "layout.json").read_text(encoding="utf-8"))
    shots = json.loads((work / "shots.json").read_text(encoding="utf-8"))
    subs = json.loads((work / "subs.json").read_text(encoding="utf-8"))
    report = json.loads((work / "layout_report.json").read_text(encoding="utf-8"))
    canvas = (cfg["canvas"]["w"], cfg["canvas"]["h"])
    duration = float(args["duration"])
    win = cfg["bands"]["center"]

    script = draft.DraftFolder(str(root)).create_draft(name, *canvas, cfg["canvas"]["fps"])
    folder = root / name
    media = folder / "media"
    media.mkdir()

    def copy(source: str, stem: str) -> str:
        target = media / f"{stem}{Path(source).suffix.lower()}"
        shutil.copy2(source, target)
        return str(target)

    # 先加的轨道在下层：中央窗素材压在带透明窗口的底图之下。
    window, band, title, footer, captions, voice = script.append_tracks([
        TrackSpec(TrackType.video, "中央窗"), TrackSpec(TrackType.video, "底图"),
        TrackSpec(TrackType.text, "标题"), TrackSpec(TrackType.text, "底部文字"),
        TrackSpec(TrackType.text, "字幕"), TrackSpec(TrackType.audio, "配音")])

    copies: dict[str, str] = {}
    for n, shot in enumerate(shots, 1):
        source = shot["asset"]
        if source not in copies:
            copies[source] = copy(source, f"shot{n:02d}")
        material = draft.VideoMaterial(copies[source])
        start, end = float(shot["start"]), float(shot["end"])
        settings = place(material.width, material.height, canvas, win, (shot.get("fit") or "cover").lower(),
                         float(shot.get("focus_y", 0.5)))
        target = span(start, end)
        if material.material_type == "photo":
            segment = draft.VideoSegment(material, target, clip_settings=settings)
        else:
            # 只给源区间，速度由源长 ÷ 目标长得出，目标时长不因速度换算而偏移。
            cin = float(shot.get("in", 0))
            source_range = span(cin, cin + (end - start) * float(shot.get("speed", 1.0)))
            segment = draft.VideoSegment(material, target, source_timerange=source_range,
                                         volume=0.0, clip_settings=settings)
        script.add_segment(segment, window)

    # 底图不含文字，标题与底部文字另成可编辑的文字轨。
    band_png = media / "band.png"
    L.render_background(cfg)[0].save(band_png)
    script.add_segment(draft.VideoSegment(str(band_png), span(0, duration)), band)

    slots = cfg["text_slots"]
    for slot, track in (("title", title), ("quote", footer)):
        block = report["blocks"].get(slot)
        if block:
            script.add_segment(text_segment(
                "\n".join(line["text"] for line in block["lines"]), 0, duration,
                cfg["fonts"][slots[slot]["font"]], block["font_size"], block_center(block["lines"]),
                canvas[1]), track)

    # 字幕按成片的同一规则断行与缩字，位置居中于字幕框。
    box, spec = cfg["bands"]["subtitle"], cfg["fonts"]["subtitle"]
    for cue in subs:
        font, lines = L.fit_block(cue["text"], spec, box["w"], box["h"])
        script.add_segment(text_segment("\n".join(lines), float(cue["start"]), float(cue["end"]), spec,
                                        font.size, box["y"] + box["h"] / 2, canvas[1]), captions)

    if args.get("audio"):
        sound = draft.AudioMaterial(copy(args["audio"], "voice"))
        script.add_segment(draft.AudioSegment(sound, span(0, min(sound.duration / draft.SEC, duration))), voice)

    card = work / "card.png"
    write_cover(card if card.is_file() else band_png, folder)
    save_draft(script, folder, draft_id, name)
    return folder


LATER = "退出剪映后运行 python tools/jianying_draft.py --register 补登记"


def export(work: Path, root: Path, name: str | None = None, register: bool = True) -> str:
    """生成草稿并尽量登记首页，返回给用户的一句说明。剪映开着时草稿照常生成，登记留到之后。"""
    if not (work / "compose_args.json").is_file():
        raise ValueError("输出目录里没有 compose_args.json；先运行 build_video.py（可加 --prepare-only）")
    draft_id = str(uuid.uuid4()).upper()
    project = json.loads((work / "project.json").read_text(encoding="utf-8"))
    title = re.sub(r"[\\/:\s]+", "", project.get("title", ""))[:16]
    folder = build(work, root, name or f"{title}-{work.name}-{draft_id[:6]}", draft_id)
    if not register:
        return f"已生成草稿（未登记首页）：{folder}"
    try:
        original = read_index(root)
        register_draft(root, json.loads((folder / "draft_meta_info.json").read_text(encoding="utf-8")), original)
    except ValueError as exc:
        mark_pending(root, folder.name)
        return f"已生成草稿：{folder}；尚未登记首页（{exc}）。{LATER}"
    return f"已生成草稿并登记剪映首页：{folder}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--work", type=Path, help="build_video.py 的输出目录")
    mode.add_argument("--register", action="store_true", help="登记之前因剪映开着而未登记的草稿")
    parser.add_argument("--name", help="草稿名，默认取标题与版本目录名")
    parser.add_argument("--draft-root", type=Path, default=DEFAULT_ROOT, help="剪映草稿目录")
    parser.add_argument("--no-register", action="store_true", help="仅生成草稿文件，不登记首页")
    args = parser.parse_args()
    root = args.draft_root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"找不到剪映草稿目录：{root}；请用 --draft-root 指定")
    if args.register:
        names = register_pending(root)
        print(f"已登记 {len(names)} 份草稿：{'、'.join(names)}" if names else "没有待登记的草稿")
    else:
        print(export(args.work, root, args.name, not args.no_register))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
