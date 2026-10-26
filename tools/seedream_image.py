#!/usr/bin/env python3
"""用 Seedream 生成一张贴片底图，保存请求与状态；不自动重复提交。"""
from __future__ import annotations

import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.error
import urllib.request

from PIL import Image
from check_credentials import load_env

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-pro-260628"


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def generate(payload: dict, work: Path, key: str | None) -> Path:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    fingerprint = hashlib.sha256(body).hexdigest()
    receipt_path = work / "receipt.json"
    output = work / "poster.png"
    if receipt_path.exists():
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if previous.get("request_sha256") != fingerprint:
            raise ValueError("输入已改变，请使用新的 --work 目录。")
        if previous.get("status") == "complete" and output.exists():
            with Image.open(output) as picture:
                picture.verify()
            return output
        raise ValueError("已有未完成请求；请先检查回执，不自动重新提交。确定重做后使用新目录。")
    if work.exists() and any(work.iterdir()):
        raise ValueError("工作目录非空，请使用新的 --work 目录。")
    if not key:
        raise ValueError("ARK_IMAGE_API_KEY ABSENT")
    work.mkdir(parents=True, exist_ok=True)
    save_json(work / "request.json", payload)
    receipt = {"status": "requesting", "request_sha256": fingerprint, "endpoint": ENDPOINT}
    # 发请求前写状态；即使进程中断，下次也不会自动再次付费提交。
    save_json(receipt_path, receipt)
    request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        receipt.update(status="failed", http_status=exc.code)
        save_json(receipt_path, receipt)
        raise ValueError(f"生图接口返回 HTTP {exc.code}，已保留回执，不自动重试。") from None
    except Exception:
        receipt.update(status="outcome_unknown")
        save_json(receipt_path, receipt)
        raise ValueError("未取得完整生图响应，结果未知；已保留回执，不自动重试。") from None

    try:
        data = result["data"]
        if len(data) != 1:
            raise ValueError("expected one image")
        raw = base64.b64decode(data[0]["b64_json"], validate=True)
        with Image.open(BytesIO(raw)) as picture:
            picture.load()
            size = list(picture.size)
            picture.convert("RGB").save(work / "poster.partial.png", format="PNG")
        (work / "poster.partial.png").replace(output)
    except Exception:
        receipt.update(status="invalid_image")
        save_json(receipt_path, receipt)
        raise ValueError("响应没有一张可用图片；已保留回执，不自动重新提交。") from None
    receipt.update(status="complete", file="poster.png", size=size)
    save_json(receipt_path, receipt)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="UTF-8 提示词文件")
    parser.add_argument("--work", required=True, help="新的结果目录")
    parser.add_argument("--env", default=".env.local")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--size", default="1080x1920")
    parser.add_argument("--dry-run", action="store_true", help="只显示请求正文，不读取 Key、不联网")
    args = parser.parse_args()
    prompt = Path(args.prompt).read_text(encoding="utf-8").strip()
    if not prompt:
        parser.error("提示词不能为空")
    payload = {"model": args.model, "prompt": prompt, "size": args.size,
               "response_format": "b64_json", "watermark": False}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    try:
        output = generate(payload, Path(args.work), load_env(Path(args.env)).get("ARK_IMAGE_API_KEY"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(output)


if __name__ == "__main__":
    main()
