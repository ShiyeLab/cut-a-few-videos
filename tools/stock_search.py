#!/usr/bin/env python3
"""按镜头需求检索 Pixabay 或 Pexels，下载候选、抽预览帧并记录来源。"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from check_credentials import load_env

ROOT = Path(__file__).resolve().parents[1]
LICENSES = {
    "pixabay": "https://pixabay.com/service/license-summary/",
    "pexels": "https://www.pexels.com/license/",
}
CENTER_W = 1080


def slug(text: str) -> str:
    return re.sub(r"[\W_]+", "-", text.lower()).strip("-")[:40] or "shot"


def api_get(request: urllib.request.Request) -> dict:
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.load(resp)


def write_json(path: Path, data: dict) -> None:
    with tempfile.TemporaryDirectory(dir=path.parent) as work:
        pending = Path(work) / path.name
        pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.replace(path)


def pixabay_search(key: str, query: str, count: int, cache: Path, lang: str = "en") -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "lang": lang, "video_type": "film", "safesearch": "true",
                                     "per_page": max(3, count)})
    # Pixabay 要求相同搜索缓存 24 小时。文件名只取搜索参数，不含账号密钥。
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(params.encode()).hexdigest() + ".json")
    if path.is_file() and time.time() - path.stat().st_mtime < 86400:
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        url = "https://pixabay.com/api/videos/?" + params + "&" + urllib.parse.urlencode({"key": key})
        data = api_get(urllib.request.Request(url))
        if not isinstance(data.get("hits"), list):
            raise ValueError("Pixabay response lacks hits")
        write_json(path, {"hits": data["hits"]})

    videos = []
    for hit in data["hits"]:
        files = [{"file_type": "video/mp4", "link": f["url"], "width": f.get("width"),
                  "height": f.get("height")} for f in hit["videos"].values() if f.get("url")]
        videos.append({"id": hit["id"], "duration": hit["duration"], "url": hit["pageURL"],
                       "user": {"name": hit["user"]}, "video_files": files})
    return videos[:count]


def pexels_search(key: str, query: str, count: int) -> list[dict]:
    params = urllib.parse.urlencode({"query": query, "per_page": count,
                                     "orientation": "portrait", "size": "medium"})
    request = urllib.request.Request("https://api.pexels.com/videos/search?" + params,
                                     headers={"Authorization": key})
    return api_get(request)["videos"]


def pick_file(video: dict) -> dict | None:
    """挑宽度够铺满中央窗的最小 mp4；都不够宽时取最大的一个。"""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    if not files:
        return None
    files.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
    wide = [f for f in files if (f.get("width") or 0) >= CENTER_W]
    return wide[0] if wide else files[-1]


def download(url: str, dest: Path, duration: float) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "cut-a-few-videos/1.0"})
    with tempfile.TemporaryDirectory(dir=dest.parent) as work:
        pending = Path(work) / dest.name
        with urllib.request.urlopen(req, timeout=120) as src, pending.open("wb") as out:
            shutil.copyfileobj(src, out)
            expected = src.headers.get("Content-Length")
            if not out.tell() or (expected and out.tell() != int(expected)):
                raise OSError("incomplete download")
        preview = pending.with_suffix(".jpg")
        seek = min(1.0, duration / 2)
        result = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seek), "-i", str(pending),
                                 "-frames:v", "1", str(preview)], capture_output=True)
        if result.returncode or not preview.is_file():
            raise ValueError("unable to decode candidate")
        pending.replace(dest)
        preview.replace(dest.with_suffix(".jpg"))


def record_path(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--env", default=str(ROOT / ".env.local"))
    ap.add_argument("--provider", choices=tuple(LICENSES))
    ap.add_argument("--per-shot", type=int, default=3)
    ap.add_argument("--out", default="projects/stock")
    args = ap.parse_args()
    config = load_env(Path(args.env))
    provider = args.provider or "pixabay"
    # 兼容旧配置：已有 Pexels 凭证、且配置文件还没有 Pixabay 字段的调用。
    if args.provider is None and "PIXABAY_API_KEY" not in config and config.get("PEXELS_API_KEY"):
        provider = "pexels"
    key_name = provider.upper() + "_API_KEY"
    if not (key := config.get(key_name)):
        print(f"缺少 {key_name}，请在所选配置文件中填写。", file=sys.stderr)
        return 2
    max_count = 200 if provider == "pixabay" else 80
    if not 1 <= args.per_shot <= max_count:
        ap.error(f"--per-shot 允许范围为 1 到 {max_count}")

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    shots = [s for s in brief["shots"] if s.get("type") == "stock"]
    folders = [slug(s["need"]) for s in shots]
    if len(set(folders)) != len(folders):
        print("多个 need 对应同一目录，请改用不同的 need。", file=sys.stderr)
        return 2
    out_root = (ROOT / args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    session = {"license": LICENSES[provider], "source": provider, "shots": []}
    failed = False
    for shot, name in zip(shots, folders):
        query = shot["query"].strip()
        if not query or (provider == "pixabay" and len(query) > 100):
            ap.error("query 不能为空；Pixabay 查询最多 100 个字符")
        folder = out_root / name
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if provider == "pixabay":
                videos = pixabay_search(key, query, args.per_shot, ROOT / "local/cache/pixabay",
                                        shot.get("lang", "en"))
            else:
                videos = pexels_search(key, query, args.per_shot)
        except (OSError, http.client.HTTPException, ValueError, KeyError) as error:
            # Pixabay 的请求 URL 含 key，绝不打印异常原文。
            code = getattr(error, "code", type(error).__name__)
            print(f"{provider} 检索失败 ({code})", file=sys.stderr)
            return 1
        saved = []
        for video in videos:
            f = pick_file(video)
            if not f:
                continue
            ident = str(video["id"])
            stem = ident if provider == "pexels" else f"pixabay-{ident}"
            path = folder / (stem + ".mp4")
            try:
                download(f["link"], path, video.get("duration") or 0)
            except (OSError, http.client.HTTPException, ValueError) as error:
                print(f"候选下载或抽帧失败 {ident} ({type(error).__name__})", file=sys.stderr)
                continue
            saved.append({
                "id": video["id"], "file": record_path(path),
                "still": record_path(path.with_suffix(".jpg")),
                "width": f.get("width"), "height": f.get("height"), "duration": video.get("duration"),
                "photographer": video["user"].get("name"), "page": video["url"],
                "license": LICENSES[provider], "requirement": shot.get("requirement"),
            })
            print(f"  {ident}  {video['url']}")
        write_json(folder / "manifest.json", {"source": provider, "need": shot["need"], "query": query,
                   "requirement": shot.get("requirement"), "candidates": saved})
        session["shots"].append({"need": shot["need"], "folder": record_path(folder), "candidates": len(saved)})
        if videos and not saved:
            failed = True
        print(f"{shot['need']}: {len(saved)} 个候选 → {folder}")
    write_json(out_root / "session.json", session)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
