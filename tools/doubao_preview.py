#!/usr/bin/env python3
"""豆包 2.0 短试音：显式语气指令，不覆盖正式配音，不自动重试。"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from check_credentials import load_env
from compose import media_duration, run
from doubao_tts import clean, save, subtitles

ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def make_payload(text: str, speaker: str, direction: str | None, rate: int) -> dict:
    if not text.strip() or len(text) > 300:
        raise ValueError("试音正文必须为 1 至 300 字符")
    if direction is not None and not direction.strip():
        raise ValueError("需要单独的演绎要求")
    if not -50 <= rate <= 100:
        raise ValueError("语速超出范围")
    payload = {"req_params": {
        "text": text, "speaker": speaker,
        "audio_params": {"format": "mp3", "sample_rate": 48000,
                         "bit_rate": 160000, "speech_rate": rate,
                         "enable_subtitle": True},
    }}
    if direction is not None:
        payload["req_params"]["additions"] = json.dumps({"context_texts": [direction]}, ensure_ascii=False)
    return payload


def receive(response, partial: Path) -> tuple[list[dict], list[dict]]:
    events, sentences, seen = [], [], set()
    completed = False
    with partial.open("wb") as audio:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                completed = True
                continue
            event = json.loads(line)
            code = event.get("code")
            if code not in (0, 20000000):
                raise RuntimeError(f"豆包试音返回 code={code}")
            chunk = event.pop("data", None)
            if chunk:
                audio.write(base64.b64decode(chunk, validate=True))
            sentence = event.get("sentence")
            if sentence and sentence.get("words"):
                identity = json.dumps(sentence["words"], sort_keys=True)
                if identity not in seen:
                    sentences.append(sentence)
                    seen.add(identity)
            events.append(event)
            if code == 20000000:
                completed = True
    if not partial.stat().st_size:
        raise ValueError("服务没有返回音频")
    # 某些版本以正常 EOF 收束；仍须逐字时间戳与完整解码验证。
    return events + [{"explicit_end_marker": completed}], sentences


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--direction", help="只含演绎要求的 UTF-8 文件；省略则制作无指令对照")
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--rate", type=int, default=-4)
    ap.add_argument("--work", required=True)
    ap.add_argument("--env", default=".env.local")
    args = ap.parse_args()
    text = Path(args.script).read_text().strip()
    direction = Path(args.direction).read_text().strip() if args.direction else None
    payload = make_payload(text, args.speaker, direction, args.rate)
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    receipt = work / "preview_receipt.json"
    output = work / "voice.mp3"
    if receipt.exists():
        state = json.loads(receipt.read_text())
        if state.get("input_sha256") != fingerprint:
            raise SystemExit("试音参数已改变，请使用新的试音目录")
        if state.get("status") == "complete" and output.exists():
            print(json.dumps({"status": "complete", "audio": str(output), "reused": True}))
            return 0
        raise SystemExit("已有未完成的试音请求；不自动重复计费，先检查本地回执与临时文件")
    key = load_env(Path(args.env)).get("VOLCENGINE_TTS_API_KEY")
    if not key:
        raise SystemExit("VOLCENGINE_TTS_API_KEY ABSENT")
    request_id = str(uuid.uuid4())
    state = {"provider": "doubao", "purpose": "voice_preview", "endpoint": ENDPOINT,
             "resource_id": "seed-tts-2.0", "speaker": args.speaker,
             "request_id": request_id, "input_sha256": fingerprint, "status": "requesting"}
    save(work / "request.json", payload)
    save(receipt, state)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json", "X-Api-Key": key,
                                          "X-Api-Resource-Id": "seed-tts-2.0",
                                          "X-Api-Request-Id": request_id})
    partial = work / "voice.partial.mp3"
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            events, sentences = receive(response, partial)
        save(work / "response.json", events)
        duration = media_duration(str(partial))
        timeline = subtitles(text, sentences, duration)
        if not timeline or clean("".join(s["text"] for s in timeline)) != clean(text):
            raise ValueError("试音时间戳未完整覆盖正文")
        run(["ffmpeg", "-v", "error", "-xerror", "-i", str(partial), "-f", "null", "-"], "试音完整解码")
        save(work / "timeline.json", timeline)
        partial.replace(output)
        state.update(status="complete", audio=str(output), duration=duration,
                     timestamps="provider_word_timestamps", subtitle_count=len(timeline))
        save(receipt, state)
    except urllib.error.HTTPError as exc:
        state.update(status="http_failed", http_status=exc.code)
        save(receipt, state)
        raise SystemExit(f"豆包试音 HTTP {exc.code}") from None
    except (OSError, ValueError, RuntimeError) as exc:
        state.update(status="incomplete", error_type=type(exc).__name__)
        save(receipt, state)
        raise SystemExit(f"试音未完成：{type(exc).__name__}；保留回执，不自动重试") from None
    print(json.dumps({"status": "complete", "audio": str(output), "duration": duration}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
