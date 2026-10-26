#!/usr/bin/env python3
"""豆包 2.0 流式配音（生产用）：整篇合成，可带语气指令，保存回执与字级时间戳。

接口特性：
  带语气指令（additions.context_texts）的只有单向流式接口；异步 /tts/submit 没有这个字段。
  本接口没有 task_id：断线即"结果未知"，不能续传，也不能当没发生过。

恢复约定：
  - 提交前先写回执（status=requesting），音频先落临时文件；
  - 成功后 status=complete，之后同输入指纹直接复用，不再联网；
  - 断网/超时 → status=unknown，保留临时文件字节数；重跑会拒绝自动重发，需人工确认；
  - 已经流式收到的音频不能续传，只能整段重发（会再计费一次）。

用法：
  python3 tools/doubao_tts_stream.py \
    --script "projects/my-video/script.txt" \
    --direction projects/my-video/direction.txt \
    --speaker zh_female_qingxinnvsheng_uranus_bigtts --rate 0 \
    --work projects/my-video/voice-v1
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from check_credentials import load_env
from compose import media_duration, run
from doubao_preview import receive
from doubao_tts import clean, save, subtitles

ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
MAX_CHARS = 900  # 留余量；超过应分段，而不是赌接口上限


def make_payload(text: str, speaker: str, direction: str | None, rate: int) -> dict:
    if not text.strip():
        raise ValueError("口播正文为空")
    if len(text) > MAX_CHARS:
        raise ValueError(f"正文 {len(text)} 字超过 {MAX_CHARS}，应先分段再合成")
    if direction is not None and not direction.strip():
        raise ValueError("演绎要求文件为空；不需要指令时不要传 --direction")
    payload = {"req_params": {
        "text": text, "speaker": speaker,
        "audio_params": {"format": "mp3", "sample_rate": 48000,
                         "bit_rate": 160000, "speech_rate": rate,
                         "enable_subtitle": True},
    }}
    if direction is not None:
        payload["req_params"]["additions"] = json.dumps(
            {"context_texts": [direction]}, ensure_ascii=False)
    return payload


def trim_events(events: list[dict]) -> list[dict]:
    """事件里带 base64 音频块，只留长度与状态，避免回执膨胀。"""
    kept = []
    for e in events:
        item = {k: v for k, v in e.items() if k not in ("data", "sentence")}
        if "data" in e:
            item["audio_chunk_b64_len"] = len(e["data"])
        if "sentence" in e:
            item["words"] = len(e["sentence"].get("words", []))
        kept.append(item)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--direction", default=None, help="只含演绎要求的 UTF-8 文件")
    ap.add_argument("--rate", type=int, default=0)
    ap.add_argument("--resource", default="seed-tts-2.0")
    ap.add_argument("--env", default=".env.local")
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    text = "\n".join(s.strip() for s in Path(args.script).read_text().splitlines()
                     if s.strip() and not s.lstrip().startswith("#"))
    direction = Path(args.direction).read_text().strip() if args.direction else None
    payload = make_payload(text, args.speaker, direction, args.rate)
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                            sort_keys=True).encode()).hexdigest()

    receipt_path = work / "tts_receipt.json"
    audio_path = work / "voice.mp3"
    if receipt_path.exists():
        state = json.loads(receipt_path.read_text())
        if state.get("input_sha256") != fingerprint:
            raise SystemExit("配音输入已改变（正文/音色/语速/指令），请使用新版本目录")
        if state.get("status") == "complete" and audio_path.exists() and (work / "timeline.json").exists():
            print(json.dumps({"status": "complete", "audio": str(audio_path), "reused": True},
                             ensure_ascii=False))
            return 0
        raise SystemExit(f"上次状态 {state.get('status')}，不自动重发。"
                         "先看 tts_receipt.json 与 voice.partial.mp3，保留本次记录；确认需要重做后，另建新配音目录")

    key = load_env(Path(args.env)).get("VOLCENGINE_TTS_API_KEY")
    if not key:
        raise SystemExit("VOLCENGINE_TTS_API_KEY ABSENT；未发起合成")

    request_id = str(uuid.uuid4())
    save(work / "tts_request.json", {"endpoint": ENDPOINT, "resource_id": args.resource,
                                     "transport": "unidirectional_stream", "body": payload})
    state = {"provider": "doubao", "transport": "unidirectional_stream", "endpoint": ENDPOINT,
             "resource_id": args.resource, "speaker": args.speaker, "rate": args.rate,
             "direction": direction, "request_id": request_id, "input_sha256": fingerprint,
             "status": "requesting", "task_id": None}
    save(receipt_path, state)

    partial = work / "voice.partial.mp3"
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "X-Api-Key": key,
                 "X-Api-Resource-Id": args.resource, "X-Api-Request-Id": request_id})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            events, sentences = receive(response, partial)
    except urllib.error.HTTPError as exc:
        state.update(status="http_failed", http_status=exc.code)
        save(receipt_path, state)
        raise SystemExit(f"豆包流式配音 HTTP {exc.code}；未自动重试") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        got = partial.stat().st_size if partial.exists() else 0
        state.update(status="unknown", error_type=type(exc).__name__, partial_bytes=got)
        save(receipt_path, state)
        raise SystemExit(f"流式配音中断（{type(exc).__name__}），已收 {got} 字节；"
                         "结果未知，不自动重发") from None

    save(work / "tts_events.json", trim_events(events))
    try:
        duration = media_duration(str(partial))
        timeline = subtitles(text, sentences, duration)
        if not timeline:
            raise ValueError("时间戳为空")
        if clean("".join(s["text"] for s in timeline)) != clean(text):
            raise ValueError("字级时间戳未完整覆盖正文")
        run(["ffmpeg", "-v", "error", "-xerror", "-i", str(partial), "-f", "null", "-"],
            "配音完整解码")
    except (ValueError, SystemExit) as exc:
        state.update(status="timeline_invalid", error=str(exc)[:300])
        save(receipt_path, state)
        raise SystemExit(f"配音结果未通过核对：{exc}；保留临时文件，不自动重发") from None

    partial.replace(audio_path)
    save(work / "timeline.json", timeline)
    save(work / "subs.json", timeline)
    state.update(status="complete", audio=str(audio_path), duration=duration,
                 timestamps="provider_word_timestamps", subtitle_count=len(timeline))
    save(receipt_path, state)
    print(json.dumps({"status": "complete", "audio": str(audio_path),
                      "duration": duration, "subtitles": len(timeline)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
