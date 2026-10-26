#!/usr/bin/env python3
"""按镜头需求搜免费素材：查 Pexels → 下候选 → 抽帧供人/Agent 看 → 记录来源与许可。

选材约定：
  - 每个补充镜头先有"可观察的画面要求"，不按标题关键词瞎选；
  - 不能只靠缩略图判断，必须抽帧看真实画面；
  - 记录原始页面、作者、素材 ID、许可依据，落盘到 projects/stock/<slug>/manifest.json。

用法：
  python3 tools/stock_search.py --brief templates/stock-brief.json
  python3 tools/stock_search.py --brief templates/stock-brief.json --per-shot 2
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.pexels.com/videos/search"
LICENSE_URL = "https://www.pexels.com/license/"


from check_credentials import load_env


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "shot"


def api_get(key: str, params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def pick_file(video: dict, want_portrait: bool) -> dict | None:
    """挑一个分辨率够用、体积适中的 mp4（竖屏窗优先竖屏或方屏）。"""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    if not files:
        return None
    files.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
    good = [f for f in files if (f.get("width") or 0) >= 720]
    return (good or files)[-1] if not want_portrait else (good or files)[0] if good else files[-1]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def frame(path: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", str(path),
                        "-frames:v", "1", str(dest)], capture_output=True)
    return p.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True)
    ap.add_argument("--env", default=str(ROOT / ".env.local"))
    ap.add_argument("--per-shot", type=int, default=3)
    ap.add_argument("--out", default="projects/stock")
    args = ap.parse_args()

    key = load_env(Path(args.env)).get("PEXELS_API_KEY", "")
    if not key:
        print("缺少 PEXELS_API_KEY（免费申请：https://www.pexels.com/api/）", file=sys.stderr)
        return 2

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    out_root = ROOT / args.out
    session = {"license": LICENSE_URL, "source": "pexels", "shots": []}

    for shot in brief["shots"]:
        if shot.get("type") != "stock":
            continue
        folder = out_root / slug(shot["need"])
        folder.mkdir(parents=True, exist_ok=True)
        data = api_get(key, {"query": shot["query"], "per_page": args.per_shot,
                             "orientation": "portrait", "size": "medium"})
        saved = []
        for v in data.get("videos", []):
            f = pick_file(v, want_portrait=True)
            if not f:
                continue
            p = folder / f"{v['id']}.mp4"
            try:
                download(f["link"], p)
            except Exception as e:
                print(f"  下载失败 {v['id']}: {type(e).__name__}", file=sys.stderr)
                continue
            still = folder / f"{v['id']}.jpg"
            frame(p, still)
            saved.append({
                "id": v["id"], "file": str(p.relative_to(ROOT)), "still": str(still.relative_to(ROOT)),
                "width": f.get("width"), "height": f.get("height"), "duration": v.get("duration"),
                "photographer": v.get("user", {}).get("name"),
                "page": v.get("url"), "license": LICENSE_URL,
                "requirement": shot.get("requirement"),
            })
        (folder / "manifest.json").write_text(
            json.dumps({"need": shot["need"], "query": shot["query"],
                        "requirement": shot.get("requirement"), "candidates": saved},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        session["shots"].append({"need": shot["need"], "folder": str(folder.relative_to(ROOT)),
                                 "candidates": len(saved)})
        print(f"{shot['need']}: {len(saved)} 个候选 → {folder}")

    (out_root / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
