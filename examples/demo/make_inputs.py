#!/usr/bin/env python3
"""生成原创几何教学输入。无下载、无配音请求、无真实图书素材。"""
from pathlib import Path
import json
import math
import subprocess
import wave
from array import array

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "examples/demo/generated"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 简单窗格图，用细线与圆点观察缓慢推近是否平稳。
    image = Image.new("RGB", (1080, 1150), "#D8E9EB")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((130, 100, 950, 1040), radius=28, fill="#F6F1E6")
    for x in range(160, 960, 100):
        draw.line((x, 130, x, 1020), fill="#A5BFC0", width=3)
    for y in range(150, 1050, 100):
        draw.line((160, y, 920, y), fill="#A5BFC0", width=3)
    draw.ellipse((360, 340, 720, 700), fill="#C98F66")
    image.save(OUT / "window.png")
    # 同一张无字底图的上下两端做贴片。
    image = Image.new("RGB", (1080, 1920), "#D8E9EB")
    draw = ImageDraw.Draw(image)
    for y in range(1920):
        shade = int(10 * math.cos(y / 1920 * math.pi * 2))
        draw.line((0, y, 1079, y), fill=(216 + shade, 230 + shade, 225 + shade))
    for x, y, radius in [(-60, 70, 190), (1040, 1820, 230), (1020, 40, 90)]:
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="#8DAEA5", width=5)
    image.save(OUT / "poster.png")
    # 真正随时间变化的测试视频，验证视频选段与静态图之间的叠化。
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=540x576:rate=30:duration=4", "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(OUT / "motion.mp4")], check=True)
    # 原创合成和弦，给“仅音乐”路径做离线示范。
    samples = array("h")
    rate = 48000
    for i in range(rate * 8):
        t = i / rate
        fade = min(1, t / 0.3, (8 - t) / 0.5)
        value = sum(math.sin(2 * math.pi * f * t) for f in (220, 277.18, 329.63)) / 3
        samples.append(round(4500 * fade * value))
    import sys
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(OUT / "music.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.tobytes())
    cfg = json.loads((ROOT / "template/layout.json").read_text(encoding="utf-8"))
    for spec in cfg["fonts"].values():
        spec["path"] = "pillow-default"
    cfg["encode"]["preset"] = "fast"
    (OUT / "layout.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("Created examples/demo/generated: 2 images, 1 clip, 1 sound, 1 layout.")


if __name__ == "__main__":
    main()
