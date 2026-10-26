#!/usr/bin/env python3
"""停顿与音量统计：同一检测条件下的客观对照，不代替听感判断。

用法：python3 tools/voice_stats.py a.mp3 b.mp3 ...
判据：低于 -40 dB、持续 ≥0.16 秒记为一次内停顿，排除开头与结尾。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def probe_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(out.strip())


def silences(path: str) -> list[tuple[float, float]]:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                           "silencedetect=noise=-40dB:d=0.16", "-f", "null", "-"],
                          capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return list(zip(starts, ends))


def volume(path: str) -> tuple[float, float]:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", proc.stderr)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", proc.stderr)
    return (float(mean.group(1)) if mean else float("nan"),
            float(peak.group(1)) if peak else float("nan"))


def analyze(path: str) -> dict:
    duration = probe_duration(path)
    pairs = silences(path)
    # 排除开头/结尾的静音，只统计“句内与句间”停顿
    inner = [(s, e) for s, e in pairs if s > 0.25 and e < duration - 0.25]
    total = sum(e - s for s, e in inner)
    longest = max((e - s for s, e in inner), default=0.0)
    mean, peak = volume(path)
    return {"file": str(Path(path)), "duration": round(duration, 3),
            "inner_pauses": len(inner), "pause_total_s": round(total, 3),
            "pause_longest_s": round(longest, 3),
            "speech_ratio": round(1 - total / duration, 3) if duration else 0,
            "mean_db": mean, "peak_db": peak}


if __name__ == "__main__":
    rows = [analyze(p) for p in sys.argv[1:]]
    w = max(len(Path(r["file"]).parent.name) for r in rows) + 2
    print(f"{'样本':<{w}}{'时长':>7}{'停顿次数':>9}{'停顿合计':>9}{'最长停顿':>9}{'说话占比':>9}")
    for r in rows:
        name = Path(r["file"]).parent.name
        print(f"{name:<{w}}{r['duration']:>7.1f}{r['inner_pauses']:>9}{r['pause_total_s']:>9.2f}"
              f"{r['pause_longest_s']:>9.2f}{r['speech_ratio']:>9.2%}")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
