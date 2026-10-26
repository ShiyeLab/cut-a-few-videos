#!/usr/bin/env python3
"""读取单条视频配置，沿用已有排版和合成工具；不调用外部服务。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import compose as C
import layout as L
from doubao_tts import clean, save


def read_json(path: str) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare(project: dict, work: Path, no_voice: bool, no_music: bool) -> argparse.Namespace:
    cfg = read_json(project["layout"])
    if (cfg["canvas"]["w"], cfg["canvas"]["h"]) != (1080, 1920):
        raise ValueError("当前成片与校验使用 1080×1920，请保留画布尺寸")
    timeline = read_json(project["timeline"])
    script = "\n".join(line.strip() for line in Path(project["script"]).read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    if not timeline or not clean(script) or clean(script) != clean("".join(x["text"] for x in timeline)):
        raise ValueError("时间轴未完整覆盖口播正文")
    cursor = 0.0
    for cue in timeline:
        start, end = float(cue["start"]), float(cue["end"])
        if start < cursor or end <= start:
            raise ValueError("时间轴有重叠、倒序或无效时长")
        cursor = end
    fps = cfg["canvas"]["fps"]
    voice = project.get("voice")
    narration = C.media_duration(voice) if voice else None
    if project.get("duration") is not None:
        duration = float(project["duration"])
    elif narration is not None:
        duration = math.ceil((narration + project.get("tail", 1.2)) * fps) / fps
    else:
        raise ValueError("没有配音文件时，需在项目配置中明确填写 duration")
    if duration <= 0 or cursor > duration + C.TOL:
        raise ValueError("字幕超出成片时长")
    if narration is not None and duration < narration - C.TOL:
        raise ValueError("目标成片比口播短，拒绝截断声音")

    transition = round(project.get("transition", 8 / fps) * fps) / fps
    scenes = read_json(project["scenes"])
    if not scenes or scenes[0].get("anchor") is not None:
        raise ValueError("首镜 anchor 必须为 null，表示从 0 秒开始")
    starts = [0.0]
    for scene in scenes[1:]:
        anchor = clean(scene.get("anchor") or "")
        matches = [x["start"] for x in timeline if anchor and clean(x["text"]).startswith(anchor)]
        if len(matches) != 1:
            raise ValueError(f"无法唯一定位口播：{scene.get('anchor')}")
        starts.append(round(float(matches[0]) * fps) / fps)
    shots = [{**scene, "start": starts[i], "end": starts[i + 1] if i + 1 < len(starts) else duration}
             for i, scene in enumerate(scenes)]
    if any(x["end"] <= x["start"] for x in shots):
        raise ValueError("镜头锚点顺序与口播不一致")

    if project.get("band_art"):
        for band, anchor in (("top", "top"), ("bottom", "bottom")):
            cfg["bands"][band].update(image=project["band_art"], image_anchor=anchor)
        cfg["bands"]["card"]["hidden"] = True
        cfg["text_slots"]["title"]["band"] = "top"
        cfg["bands"]["top"]["text_box"] = {"x": 84, "y": 92, "w": 912, "h": 196}
        cfg["bands"]["bottom"]["text_box"] = {"x": 70, "y": 1580, "w": 940, "h": 170}
        for key in ("title", "quote"):
            cfg["fonts"][key]["stroke_width"] = 3
            cfg["fonts"][key]["shadow"] = {"dx": 0, "dy": 3, "blur": 7,
                                           "opacity": 0.5, "color": cfg["fonts"][key]["stroke_color"]}
    cfg["editing"] = {"transition_seconds": transition}
    subs = []
    for i, cue in enumerate(timeline):
        start = max(0, float(cue["start"]) - 0.03)
        end = duration if i == len(timeline) - 1 else min(
            float(cue["end"]) + 0.12, max(0, float(timeline[i + 1]["start"]) - 0.03))
        subs.append({"start": start, "end": end, "text": cue["text"]})
    save(work / "project.json", project)
    save(work / "layout.json", cfg)
    save(work / "shots.json", shots)
    save(work / "subs.json", subs)
    ns = argparse.Namespace(config=str(work / "layout.json"), card=str(work / "card.png"),
        shots=str(work / "shots.json"), subs=str(work / "subs.json"),
        audio=None if no_voice else voice,
        music=None if no_music else project.get("music"), no_music=no_music,
        music_gain=float(project.get("music_gain", -14)), duration=duration,
        transition=transition, out=str(work / "video.mp4"), work=str(work))
    C.load_shots(ns, duration)
    card, report = L.render_card(cfg, project["title"], project.get("footer", ""))
    if report["overflow"]:
        raise ValueError("标题或底部文字超框")
    card.save(work / "card.png")
    save(work / "layout_report.json", report)
    C.build_subtitle_layers(cfg, subs, work)
    save(work / "compose_args.json", vars(ns))
    return ns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--work", required=True, help="新的输出目录；不覆盖已有版本")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-voice", action="store_true")
    parser.add_argument("--no-music", action="store_true")
    args = parser.parse_args()
    project = read_json(args.project)
    work = Path(args.work)
    if work.exists():
        raise SystemExit("输出目录已存在，请换新版本；手改已有 JSON 后请直接运行 compose.py")
    work.mkdir(parents=True)
    ns = prepare(project, work, args.no_voice, args.no_music)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "work": str(work), "duration": ns.duration}))
    else:
        result = C.compose(ns)
        save(work / "verify.json", result["verification"])
        save(work / "result.json", result)
        print(json.dumps({"output": result["output"], "duration": result["duration"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
