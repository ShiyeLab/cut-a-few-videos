#!/usr/bin/env python3
"""用 Pillow 渲染上下贴片、标题与字幕，再交给 compose.py 合成。
字体、坐标、配色来自 layout.json；底图可用同一张海报的上下两端。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
NO_LINE_START = set("。，、！？；：》」』）】…·%")
NO_LINE_END = set("《「『（【")
BREAK_PUNCT = "，。、；：！？…,"


def hex_rgba(value: str) -> tuple[int, int, int, int]:
    v = value.lstrip("#")
    if len(v) == 6:
        v += "FF"
    if len(v) != 8:
        raise ValueError(f"颜色格式应为 #RRGGBB 或 #RRGGBBAA，收到 {value!r}")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]


def get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in FONT_CACHE:
        if path == "pillow-default":
            FONT_CACHE[key] = ImageFont.load_default(size=size)
            return FONT_CACHE[key]
        if not os.path.exists(path):
            raise SystemExit(f"字体文件不存在：{path}")
        FONT_CACHE[key] = ImageFont.truetype(path, size)
    return FONT_CACHE[key]


def text_width(font: ImageFont.FreeTypeFont, s: str) -> int:
    return int(font.getlength(s))


def _wrap_one(text: str, font: ImageFont.FreeTypeFont, max_width: int,
              max_chars: int | None) -> list[str]:
    """单段断行：优先在标点处断，绝不以禁则标点起行。"""
    if not text:
        return []
    fit = 0
    for i in range(len(text)):
        if text_width(font, text[:i + 1]) > max_width or (max_chars is not None and i + 1 > max_chars):
            break
        fit = i + 1
    if fit >= len(text):
        return [text]
    if fit == 0:
        fit = 1
    cut = fit
    for j in range(fit - 1, max(int(fit * 0.5) - 1, 0), -1):
        if text[j] in BREAK_PUNCT:
            cut = j + 1
            break
    if cut == fit:
        while cut > 1 and text[cut] in NO_LINE_START:
            cut -= 1
        while cut > 1 and text[cut - 1] in NO_LINE_END:
            cut -= 1
    return [text[:cut]] + _wrap_one(text[cut:], font, max_width, max_chars)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int,
              max_chars: int | None = None) -> list[str]:
    lines: list[str] = []
    for seg in text.strip().split("\n"):
        if seg.strip():
            lines.extend(_wrap_one(seg.strip(), font, max_width, max_chars))
    return lines


def fit_block(text: str, spec: dict, box_w: int, box_h: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """从基准字号往下试，直到行数 ≤ max_lines 且高度 ≤ box_h。绝不静默截断。"""
    max_chars = spec.get("max_chars_per_line")
    size = int(spec["size"])
    min_size = int(spec.get("min_size", size))
    max_lines = int(spec.get("max_lines", 2))
    line_gap = int(spec.get("line_gap", 12))
    stroke = int(spec.get("stroke_width", 0) or 0)
    last_error = ""
    while size >= min_size:
        font = get_font(spec["path"], size)
        lines = wrap_text(text, font, box_w - 2 * stroke, max_chars)
        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        total_h = line_h * len(lines) + line_gap * (len(lines) - 1) + 2 * stroke
        widest = max((text_width(font, ln) for ln in lines), default=0)
        if len(lines) <= max_lines and total_h <= box_h and widest <= box_w - 2 * stroke:
            return font, lines
        last_error = f"size={size} lines={len(lines)} h={total_h}px 最宽={widest}px"
        size -= 2
    raise SystemExit(
        "文字放不下，且缩到最小字号仍超框——必须改文案或改版式，不能截断。\n"
        f"  文本: {text[:60]}{'...' if len(text) > 60 else ''}\n  最后一次: {last_error}"
    )


def measure_block(box: tuple[int, int, int, int], font: ImageFont.FreeTypeFont,
                  lines: list[str], spec: dict) -> list[dict]:
    """按字体真实行高（ascent+descent）排版，避免用字号估算导致贴边或越界。"""
    x, y, w, h = box
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    line_gap = int(spec.get("line_gap", 12))
    total_h = line_h * len(lines) + line_gap * (len(lines) - 1)
    cursor_y = y + (h - total_h) / 2
    boxes = []
    for line in lines:
        w_line = text_width(font, line)
        boxes.append({"text": line, "x": int(x + (w - w_line) / 2), "y": int(cursor_y),
                      "w": w_line, "h": line_h})
        cursor_y += line_h + line_gap
    return boxes


def draw_block(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], font: ImageFont.FreeTypeFont,
               lines: list[str], spec: dict) -> list[dict]:
    boxes = measure_block(box, font, lines, spec)
    s = spec.get("scrim")
    if s and boxes:
        px, py = int(s.get("padding_x", 0)), int(s.get("padding_y", 0))
        draw.rounded_rectangle(
            [min(b["x"] for b in boxes) - px, min(b["y"] for b in boxes) - py,
             max(b["x"] + b["w"] for b in boxes) + px, max(b["y"] + b["h"] for b in boxes) + py],
            radius=int(s.get("radius", 16)), fill=hex_rgba(s["fill"]))
    stroke_w = int(spec.get("stroke_width", 0) or 0)
    stroke_c = hex_rgba(spec.get("stroke_color", "#000000"))
    color = hex_rgba(spec["color"])
    for b in boxes:
        draw.text((b["x"], b["y"]), b["text"], font=font, fill=color,
                  stroke_width=stroke_w, stroke_fill=stroke_c if stroke_w else None)
    return boxes


def band_box(cfg: dict, name: str, pad_x: int = 36, pad_y: int = 22) -> tuple[int, int, int, int]:
    b = cfg["bands"][name]
    tb = b.get("text_box")
    if tb:
        return (tb["x"], tb["y"], tb["w"], tb["h"])
    return (b["x"] + pad_x, b["y"] + pad_y, b["w"] - 2 * pad_x, b["h"] - 2 * pad_y)


def cover_crop(image: Image.Image, w: int, h: int, anchor: str = "center") -> Image.Image:
    """等比放大到覆盖目标框，再按锚点裁切。"""
    scale = max(w / image.width, h / image.height)
    resized = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))),
                           Image.LANCZOS)
    x = (resized.width - w) // 2
    y = {"top": 0, "bottom": resized.height - h}.get(anchor, (resized.height - h) // 2)
    return resized.crop((x, y, x + w, y + h))


def render_background(cfg: dict) -> tuple[Image.Image, list[dict]]:
    """色块或贴图底 + 可选卡片；中央窗留全透明供素材透出。

    条带支持三种写法：纯色 fill；整幅海报 image + image_anchor（top/bottom/center）；
    hidden 直接跳过（B 版去卡片）。
    """
    W, H = cfg["canvas"]["w"], cfg["canvas"]["h"]
    base = hex_rgba(cfg.get("theme", {}).get("band", "#000000"))
    img = Image.new("RGBA", (W, H), base)
    d = ImageDraw.Draw(img)
    parts = []

    for name in ("top", "bottom", "card"):
        b = cfg["bands"][name]
        box = [b["x"], b["y"], b["w"], b["h"]]
        if b.get("hidden"):
            parts.append({"band": name, "box": box, "mode": "hidden"})
            continue
        if b.get("image"):
            art = Image.open(b["image"]).convert("RGB")
            img.paste(cover_crop(art, b["w"], b["h"], b.get("image_anchor", "center")),
                      (b["x"], b["y"]))
            parts.append({"band": name, "box": box, "mode": "image", "file": b["image"]})
            continue
        fill = hex_rgba(b.get("fill", "#00000000"))
        if fill[3] == 0:
            parts.append({"band": name, "box": box, "mode": "transparent"})
            continue
        if int(b.get("radius", 0)):
            d.rounded_rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]],
                                radius=int(b["radius"]), fill=fill)
        else:
            d.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], fill=fill)
        parts.append({"band": name, "box": box, "mode": "fill"})

    # 中央窗挖空
    win = cfg["bands"]["center"]
    hole = Image.new("RGBA", (win["w"], win["h"]), (0, 0, 0, 0))
    mask = Image.new("L", (win["w"], win["h"]), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, win["w"] - 1, win["h"] - 1],
                                           radius=int(win["radius"]), fill=255)
    img.paste(hole, (win["x"], win["y"]), mask)
    return img, parts


def render_center_mask(cfg: dict, path: str) -> str:
    c = cfg["bands"]["center"]
    mask = Image.new("L", (c["w"], c["h"]), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, c["w"] - 1, c["h"] - 1],
                                           radius=int(c["radius"]), fill=255)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    mask.save(path)
    return path


def _check_overflow(report: dict, name: str, box: tuple[int, int, int, int],
                    boxes: list[dict], safe_bottom: int | None = None) -> None:
    if not boxes:
        return
    x, y, w, h = box
    left = min(b["x"] for b in boxes)
    right = max(b["x"] + b["w"] for b in boxes)
    top = min(b["y"] for b in boxes)
    bottom = max(b["y"] + b["h"] for b in boxes)
    if left < x or right > x + w or top < y or bottom > y + h:
        report["overflow"].append({"block": name, "text_box": [x, y, w, h],
                                   "content": [left, top, right - left, bottom - top]})
    if safe_bottom and bottom > safe_bottom:
        report["overflow"].append({"block": name, "reason": "进入平台安全区",
                                   "bottom": bottom, "safe": safe_bottom})


def render_card(cfg: dict, title: str, quote: str) -> tuple[Image.Image, dict]:
    W, H = cfg["canvas"]["w"], cfg["canvas"]["h"]
    img, parts = render_background(cfg)
    d = ImageDraw.Draw(img)
    report: dict = {"overflow": [], "blocks": {}, "parts": parts,
                    "center_window": dict(cfg["bands"]["center"]),
                    "safe_area_bottom": cfg.get("safe_area", {}).get("bottom")}
    slots = cfg["text_slots"]
    for slot, text in (("title", title), ("quote", quote)):
        if not text:
            continue
        spec = cfg["fonts"][slots[slot]["font"]]
        box = band_box(cfg, slots[slot]["band"])
        font, lines = fit_block(text, spec, box[2], box[3])
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        boxes = draw_block(ImageDraw.Draw(layer), box, font, lines, spec)
        shadow = spec.get("shadow")
        if shadow:  # 压在艺术底上时用柔和投影换清晰度，不用大面积白光
            alpha = layer.split()[3].point(lambda a: int(a * float(shadow.get("opacity", 0.55))))
            tint = Image.new("RGBA", (W, H), hex_rgba(shadow.get("color", "#2B4F57")))
            tint.putalpha(alpha)
            tint = tint.filter(ImageFilter.GaussianBlur(float(shadow.get("blur", 6))))
            img.alpha_composite(tint, (int(shadow.get("dx", 0)), int(shadow.get("dy", 3))))
        img.alpha_composite(layer)
        report["blocks"][slot] = {"font_size": font.size, "lines": boxes}
        _check_overflow(report, slot, box, boxes, report["safe_area_bottom"])
    return img, report


def render_subtitle_layer(cfg: dict, text: str) -> tuple[Image.Image, dict]:
    W, H = cfg["canvas"]["w"], cfg["canvas"]["h"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = cfg["bands"]["subtitle"]
    box = (s["x"], s["y"], s["w"], s["h"])
    spec = cfg["fonts"]["subtitle"]
    font, lines = fit_block(text, spec, box[2], box[3])
    boxes = draw_block(d, box, font, lines, spec)
    report = {"text": text, "font_size": font.size, "lines": boxes, "box": list(box), "overflow": []}
    _check_overflow(report, "subtitle", box, boxes)
    return img, report


def main() -> int:
    ap = argparse.ArgumentParser(description="固定版式图层渲染")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("card")
    p.add_argument("--config", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--quote", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--report")

    p2 = sub.add_parser("sub")
    p2.add_argument("--config", required=True)
    p2.add_argument("--text", required=True)
    p2.add_argument("--out", required=True)

    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))

    if args.cmd == "card":
        img, report = render_card(cfg, args.title, args.quote)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        img.save(args.out)
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"out": args.out, "overflow": report["overflow"],
                          "sizes": {k: v["font_size"] for k, v in report["blocks"].items()}},
                         ensure_ascii=False))
        return 1 if report["overflow"] else 0

    if args.cmd == "sub":
        img, report = render_subtitle_layer(cfg, args.text)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        img.save(args.out)
        print(json.dumps({k: report[k] for k in ("font_size", "overflow")}, ensure_ascii=False))
        return 1 if report["overflow"] else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
