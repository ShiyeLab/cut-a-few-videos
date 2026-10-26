#!/usr/bin/env python3
"""固定版式合成：标题卡、多镜头中央画面、字幕、独立人声与音乐。
镜头表的 start/end 是成片时间（秒），in 是素材起点；从 0 连续铺至片尾。
用法与输入格式见 docs/工程说明.md。所有媒体路径相对仓库根目录。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402
from layout import render_subtitle_layer  # noqa: E402

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TOL = 0.06  # 镜头表总长与音频时长的允许误差（秒）


def run(cmd: list[str], desc: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{desc} 失败 (exit {proc.returncode})\n命令: {' '.join(cmd)}\n"
                         f"--- stderr ---\n{proc.stderr[-3000:]}")
    return proc


def probe(path: str) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-print_format", "json",
                           "-show_format", "-show_streams", path], "ffprobe").stdout)


def media_duration(path: str) -> float:
    return float(probe(path)["format"]["duration"])


def fit_statements(src: str, dst: str, win: dict, fps: int, spec: dict) -> list[str]:
    """一个镜头的缩放处理：cover 裁切填满 / contain 补底色 / blur 虚化背景 + 完整前景。"""
    w, h = win["w"], win["h"]
    fit = (spec.get("fit") or "cover").lower()
    if fit == "blur":
        return [
            f"[{src}]split=2[{dst}bg0][{dst}fg0]",
            f"[{dst}bg0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"gblur=sigma=26,eq=brightness=-0.06[{dst}bg]",
            f"[{dst}fg0]scale={w}:{h}:force_original_aspect_ratio=decrease[{dst}fg]",
            f"[{dst}bg][{dst}fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}[{dst}]",
        ]
    if fit == "contain":
        return [f"[{src}]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0B1B2B,setsar=1,fps={fps}[{dst}]"]
    focus = (spec.get("focus") or "center").lower()
    x = {"left": "0", "right": "in_w-out_w"}.get(focus, "(in_w-out_w)/2")
    return [f"[{src}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:{x}:(in_h-out_h)/2,setsar=1,fps={fps}[{dst}]"]


def load_shots(args: argparse.Namespace, duration: float) -> list[dict]:
    if args.shots:
        shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    else:
        shots = [{"asset": args.center, "start": 0.0, "end": duration,
                  "in": args.center_in, "fit": args.center_fit, "focus": args.center_focus}]

    total = 0.0
    for i, s in enumerate(shots):
        s.setdefault("start", round(total, 3))
        if "end" not in s:
            raise SystemExit(f"第 {i + 1} 个镜头缺少 end（成片时间轴终点）")
        if s["end"] <= s["start"]:
            raise SystemExit(f"第 {i + 1} 个镜头时间非法: {s['start']} → {s['end']}")
        if not Path(s["asset"]).exists():
            raise SystemExit(f"第 {i + 1} 个镜头素材不存在: {s['asset']}")
        total = float(s["end"])

    if abs(total - duration) > TOL:
        raise SystemExit(
            f"镜头表总长 {total:.2f}s 与音频 {duration:.2f}s 不一致（容差 {TOL}s）。\n"
            "声画必须等长：先定音频，再按句切镜头，不要留空白或截断。")
    if abs(shots[0]["start"]) > TOL:
        raise SystemExit(f"第一个镜头必须从 0 开始，当前 {shots[0]['start']}")
    for i in range(len(shots) - 1):
        if abs(shots[i]["end"] - shots[i + 1]["start"]) > TOL:
            raise SystemExit(f"镜头 {i + 1} 与 {i + 2} 之间有空洞或重叠："
                             f"{shots[i]['end']} vs {shots[i + 1]['start']}")
    return shots


def build_subtitle_layers(cfg: dict, subs: list[dict], work: Path) -> list[tuple[str, float, float]]:
    layer_dir = work / "subs"
    layer_dir.mkdir(parents=True, exist_ok=True)
    out, problems = [], []
    for i, item in enumerate(subs):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        start, end = float(item["start"]), float(item["end"])
        if end <= start:
            raise SystemExit(f"第 {i + 1} 条字幕时间非法: {start} → {end}")
        p = layer_dir / f"{i + 1:04d}.png"
        img, rep = render_subtitle_layer(cfg, text)
        img.save(p)
        if rep["overflow"]:
            problems.append({"index": i + 1, "text": text, "overflow": rep["overflow"]})
        out.append((str(p), start, end))
    if problems:
        raise SystemExit("字幕超框，必须改文案或改版式（不允许静默截断）：\n"
                         + json.dumps(problems, ensure_ascii=False, indent=2))
    return out


def render_center(shots: list[dict], cfg: dict, duration: float, work: Path,
                  transition: float) -> Path:
    """只给中央内容窗做叠化；重叠所需时长加在前镜尾部，不缩短成片。"""
    fps, win = cfg["canvas"]["fps"], cfg["bands"]["center"]
    transition = round(transition * fps) / fps
    if transition < 0:
        raise SystemExit("转场时长不能为负")
    inputs, filters, labels = [], [], []
    for n, shot in enumerate(shots):
        span = float(shot["end"]) - float(shot["start"])
        if transition >= span:
            raise SystemExit("转场时长必须短于镜头")
        # 每个非末镜额外保留转场尾段；xfade 后总长仍等于原口播时间轴。
        length = span + (transition if n < len(shots) - 1 else 0)
        source = shot["asset"]
        if Path(source).suffix.lower() in IMAGE_EXT:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", source]
            cin, speed = 0.0, 1.0
        else:
            cin = float(shot.get("in", 0))
            speed = float(shot.get("speed", 1.0))
            if not 0.5 <= speed <= 2.0:
                raise SystemExit("镜头速度必须在 0.5 至 2 倍之间")
            if cin < 0 or cin + length * speed > media_duration(source) + TOL:
                raise SystemExit(f"镜头 {n + 1} 的源区间（含转场）超出原片")
            inputs += ["-threads", "2", "-i", source]
        filters.append(f"[{n}:v]trim=start={cin:.6f}:duration={length * speed:.6f},"
                       f"setpts=(PTS-STARTPTS)/{speed:.6f}[sr{n}]")
        zoom = float(shot.get("zoom") or 0) if Path(source).suffix.lower() in IMAGE_EXT else 0
        # 在较大画布上计算裁切位置，再缩回输出尺寸，避免微小推近逐像素跳动。
        fit_win = {**win, "w": win["w"] * 4, "h": win["h"] * 4} if zoom else win
        filters.extend(fit_statements(f"sr{n}", f"fit{n}", fit_win, fps, shot))
        tail = f"fit{n}"
        if zoom:
            frames = max(1, round(length * fps))
            progress = f"min(on/{max(1, frames - 1)},1)"
            eased = f"({progress})*({progress})*(3-2*({progress}))"
            filters.append(
                f"[fit{n}]format=yuv444p,zoompan=z='1+{zoom:.6f}*({eased})':"
                f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:"
                f"s={win['w']}x{win['h']}:fps={fps}[zoom{n}]")
            tail = f"zoom{n}"
        filters.append(f"[{tail}]format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[shot{n}]")
        labels.append(f"shot{n}")
    last = labels[0]
    if transition:
        for n in range(1, len(shots)):
            offset = round(float(shots[n]["start"]) * fps) / fps
            filters.append(f"[{last}][shot{n}]xfade=transition=fade:duration={transition:.6f}:"
                           f"offset={offset:.6f}[join{n}]")
            last = f"join{n}"
    elif len(shots) > 1:
        filters.append("".join(f"[{lb}]" for lb in labels) + f"concat=n={len(labels)}:v=1:a=0[joined]")
        last = "joined"
    out = work / "center.mp4"
    temp = work / "center.partial.mp4"
    run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-filter_complex_threads", "1", *inputs,
         "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-an", "-t", f"{duration:.6f}",
         "-c:v", "libx264", "-threads", "4", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
         "-r", str(fps), "-movflags", "+faststart", str(temp)], "中央画面与转场")
    if abs(media_duration(str(temp)) - duration) > TOL:
        raise SystemExit("中央画面时长不符，未用于正式成片")
    temp.replace(out)
    return out


def normalize_audio(source: str, out: Path, target: float, duration: float,
                    loop: bool = False, fade: bool = False) -> None:
    inputs = (["-stream_loop", "-1"] if loop else []) + ["-i", source]
    trim = f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS"
    measure = run(["ffmpeg", "-hide_banner", "-v", "info", *inputs, "-vn", "-af",
                   f"{trim},loudnorm=I={target}:TP=-2:LRA=11:print_format=json",
                   "-f", "null", "-"], "测量音量")
    stats = json.loads(re.findall(r'\{\s*"input_i".*?\}', measure.stderr, re.S)[-1])
    if not math.isfinite(float(stats["input_i"])):
        raise SystemExit("音频没有可用声音")
    norm = (f"loudnorm=I={target}:TP=-2:LRA=11:measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true")
    samples = round(duration * 48000)
    af = (f"{trim},{norm},aresample=48000,asetpts=N/SR/TB,"
          f"apad=whole_len={samples},atrim=end_sample={samples}")
    if fade:
        af += f",afade=t=in:d=0.6,afade=t=out:st={max(0,duration-1.2):.6f}:d=1.2"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-vn", "-af", af, "-ar", "48000", "-ac", "2",
         "-c:a", "pcm_s16le", str(out)], "统一音量")


def mix_soundtrack(args: argparse.Namespace, cfg: dict, duration: float, work: Path) -> Path:
    """四种组合：人声+音乐 / 只有人声 / 只有音乐 / 全静音。"""
    target = float(cfg["audio"]["lufs"])
    soundtrack = work / "soundtrack.wav"
    use_music = bool(args.music) and not getattr(args, "no_music", False)

    voice = None
    if args.audio:
        voice = work / "voice_normalized.wav"
        normalize_audio(args.audio, voice, target, duration)

    music = None
    if use_music:
        music = work / "music_normalized.wav"
        normalize_audio(args.music, music, target + args.music_gain, duration, loop=True, fade=True)

    samples = round(duration * 48000)
    if voice and music:
        graph = ("[0:a]asplit=2[voice][key];"
                 "[1:a][key]sidechaincompress=threshold=0.13:ratio=2:attack=35:release=450[duck];"
                 "[voice][duck]amix=inputs=2:duration=longest:normalize=0,"
                 "alimiter=limit=0.891:level=false:latency=true,asetpts=N/SR/TB,"
                 f"apad=whole_len={samples},atrim=end_sample={samples}[mix]")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-i", str(music),
             "-filter_complex", graph, "-map", "[mix]", "-ar", "48000", "-ac", "2",
             "-c:a", "pcm_s16le", str(soundtrack)], "混合口播与音乐")
    elif voice:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-c:a", "copy", str(soundtrack)],
            "保存口播")
    elif music:
        # 无人声：音乐单独成轨，不再做闪避，峰值限制与片长对齐
        run(["ffmpeg", "-v", "error", "-y", "-i", str(music), "-af",
             f"alimiter=limit=0.891:level=false:latency=true,asetpts=N/SR/TB,"
             f"apad=whole_len={samples},atrim=end_sample={samples}",
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(soundtrack)], "生成音乐轨")
    else:
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.6f}",
             "-c:a", "pcm_s16le", str(soundtrack)], "生成静音轨")
    return soundtrack


def subtitle_track(layers: list[tuple[str, float, float]], cfg: dict,
                   duration: float, work: Path) -> Path:
    """按字幕实际起止渲染一条透明轨，避免同时循环解码二十多张全屏 PNG。"""
    fps = cfg["canvas"]["fps"]
    blank = work / "subs" / "blank.png"
    blank.parent.mkdir(parents=True, exist_ok=True)
    image, _ = render_subtitle_layer(cfg, "")
    image.save(blank)
    entries, cursor = [], 0
    for file, start, end in layers:
        first, last = round(start * fps), round(end * fps)
        if first < cursor:
            raise SystemExit("字幕有重叠")
        if first > cursor:
            entries.append((blank, first - cursor))
        if last > first:
            entries.append((Path(file), last - first))
        cursor = last
    tail = round(duration * fps) - cursor
    if tail < 0:
        raise SystemExit("字幕超出成片")
    if tail:
        entries.append((blank, tail))
    lines = ["ffconcat version 1.0"]
    for file, frames in entries:
        quoted = str(file.resolve()).replace("'", "'\\''")
        lines += [f"file '{quoted}'", f"option framerate {fps}", f"duration {frames/fps:.9f}"]
    quoted = str(blank.resolve()).replace("'", "'\\''")
    lines += [f"file '{quoted}'", f"option framerate {fps}"]
    listing = work / "subtitle_frames.ffconcat"
    listing.write_text("\n".join(lines) + "\n")
    output = work / "subtitles.mov"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", f"fps={fps}", "-t", f"{duration:.6f}", "-c:v", "qtrle", "-pix_fmt", "argb",
         "-threads", "4", str(output)], "生成透明字幕轨")
    return output


def compose(args: argparse.Namespace) -> dict:
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    W, H, FPS = cfg["canvas"]["w"], cfg["canvas"]["h"], cfg["canvas"]["fps"]
    win = cfg["bands"]["center"]
    enc, a = cfg["encode"], cfg["audio"]

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    if args.duration:
        duration = float(args.duration)
    elif args.audio:
        duration = media_duration(args.audio)
    else:
        raise SystemExit("没有口播时必须用 --duration 指定片长")
    if args.audio and duration < media_duration(args.audio) - TOL:
        raise SystemExit("目标成片比口播短，拒绝截断声音")
    shots = load_shots(args, duration)
    sub_layers = build_subtitle_layers(
        cfg, json.loads(Path(args.subs).read_text(encoding="utf-8")), work) if args.subs else []

    transition = getattr(args, "transition", None)
    if transition is None:
        transition = cfg.get("editing", {}).get("transition_seconds", 0.0)
    center = getattr(args, "prepared_center", None) or render_center(shots, cfg, duration, work, transition)
    soundtrack = getattr(args, "prepared_soundtrack", None) or mix_soundtrack(args, cfg, duration, work)
    if any(abs(media_duration(str(p)) - duration) > TOL for p in (center, soundtrack)):
        raise SystemExit("中央画面或混音时长不匹配")
    subtitle_movie = subtitle_track(sub_layers, cfg, duration, work)
    inputs = ["-loop", "1", "-framerate", str(FPS), "-i", args.card,
              "-i", str(center), "-i", str(soundtrack), "-i", str(subtitle_movie)]
    filters: list[str] = []
    audio_idx, mask_idx = 2, 4
    inputs += ["-loop", "1", "-framerate", str(FPS), "-i",
               L.render_center_mask(cfg, str(work / "center_mask.png"))]

    filters.append(f"[{mask_idx}:v]format=gray[mask]")
    filters.append("[1:v][mask]alphamerge[center]")
    filters.append(f"[0:v][center]overlay=x={win['x']}:y={win['y']}:eof_action=repeat[base]")

    filters.append("[base][3:v]overlay=0:0:eof_action=pass,format=yuv420p[vout]")

    out = str(Path(args.out))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    temp = str(Path(out).with_name(Path(out).stem + ".partial.mp4"))
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-filter_complex_threads", "1", *inputs,
           "-filter_complex", ";".join(filters),
           "-map", "[vout]", "-map", f"{audio_idx}:a",
           "-t", f"{duration:.3f}", "-r", str(FPS),
           "-c:v", enc["vcodec"], "-threads", "4", "-crf", str(enc["crf"]), "-preset", enc["preset"],
           "-pix_fmt", "yuv420p", "-color_range", "tv", "-profile:v", "high", "-level", "4.1",
           "-c:a", enc["acodec"], "-b:a", enc["abitrate"], "-ar", str(a["sample_rate"]), "-ac", "2",
           "-movflags", "+faststart", temp]
    (work / "render_command.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2))
    run(cmd, "ffmpeg 合成")
    report = verify(temp, None, None, duration)
    if not all(report[k] for k in ("decode_ok", "geometry_ok", "audio_ok", "duration_ok")):
        raise SystemExit("最终文件校验未通过，未覆盖正式成片")
    Path(temp).replace(out)
    report["path"] = out

    return {"output": out, "duration": round(duration, 3), "shots": len(shots),
            "shot_table": [{"start": s["start"], "end": s["end"], "asset": Path(s["asset"]).name,
                            "fit": s.get("fit", "cover"), "in": s.get("in")} for s in shots],
            "subs_count": len(sub_layers), "music": args.music, "transition_seconds": transition,
            "verification": report}


def verify(path: str, report_path: Path | None, stills_dir: Path | None,
           expected_duration: float | None = None) -> dict:
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dec = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
                         capture_output=True, text=True)
    res = {
        "path": path,
        "duration": round(float(info["format"]["duration"]), 3),
        "size_mb": round(int(info["format"]["size"]) / 1048576, 2),
        "video": {"codec": v["codec_name"], "w": v["width"], "h": v["height"],
                  "fps": v["r_frame_rate"], "pix_fmt": v.get("pix_fmt")} if v else None,
        "audio": {"codec": au["codec_name"], "channels": au["channels"],
                  "sample_rate": au["sample_rate"]} if au else None,
        "decode_ok": dec.returncode == 0 and not dec.stderr.strip(),
        "decode_stderr": dec.stderr.strip()[:500],
    }
    res["geometry_ok"] = bool(v and v["width"] == 1080 and v["height"] == 1920)
    res["audio_ok"] = au is not None
    if expected_duration is not None:
        res["expected_duration"] = round(expected_duration, 3)
        res["duration_ok"] = bool(v and au and all(
            abs(float(stream.get("duration", 0)) - expected_duration) <= TOL
            for stream in (v, au)))

    if stills_dir:
        stills_dir.mkdir(parents=True, exist_ok=True)
        for old in stills_dir.glob("frame_*.jpg"):
            old.unlink()
        dur = float(info["format"]["duration"])
        shots = []
        for frac in (0.05, 0.3, 0.55, 0.8, 0.95):
            t = dur * frac
            p = stills_dir / f"frame_{int(t * 10):04d}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path,
                 "-frames:v", "1", str(p)], "抽帧")
            shots.append(str(p))
        res["stills"] = shots

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="固定版式本地合成（多镜头）")
    ap.add_argument("--config", default="template/layout.json")
    ap.add_argument("--card", required=True)
    ap.add_argument("--shots", default=None, help="镜头表 JSON；省略则用 --center 单镜头铺满")
    ap.add_argument("--center", default=None)
    ap.add_argument("--center-in", type=float, default=0.0)
    ap.add_argument("--center-out", type=float, default=None)
    ap.add_argument("--center-fit", choices=["cover", "contain", "blur"], default="cover")
    ap.add_argument("--center-focus", choices=["left", "center", "right"], default="center")
    ap.add_argument("--audio", default=None, help="口播音轨；不给则输出无人声版（必须给 --duration）")
    ap.add_argument("--subs", default=None)
    ap.add_argument("--music", default=None)
    ap.add_argument("--no-music", action="store_true", help="不加配乐；省略 --audio 时为全静音版")
    ap.add_argument("--music-gain", type=float, default=-14.0)
    ap.add_argument("--transition", type=float, default=None, help="中央画面叠化秒数")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--review-json", default=None)
    args = ap.parse_args()

    if not args.shots and not args.center:
        raise SystemExit("必须给 --shots 或 --center")

    print(json.dumps(compose(args), ensure_ascii=False))
    if args.verify:
        review = Path(args.review_json) if args.review_json else Path(args.work) / "verify.json"
        res = verify(args.out, review, Path(args.work) / "stills")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if (res["decode_ok"] and res["geometry_ok"] and res["audio_ok"]) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
