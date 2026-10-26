#!/usr/bin/env python3
"""豆包异步配音：整篇合成，保存回执，按真实字级时间戳生成字幕。

首次提交只执行一次；再次运行只查询已保存的 task_id。不会降级为系统朗读。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from check_credentials import load_env
from compose import media_duration

BASE = "https://openspeech.bytedance.com/api/v3/tts"
DEFAULT_SPEAKER = "zh_male_cixingjieshuonan_uranus_bigtts"


def save(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def clean(text: str) -> str:
    return "".join(c for c in text if c.isalnum())


def subtitles(text: str, sentences: list[dict], duration: float) -> list[dict]:
    chars = []
    for sentence in sentences:
        for word in sentence.get("words", []):
            start, end = float(word["startTime"]), float(word["endTime"])
            if start < 0 or end < start or end > duration + 0.1:
                raise ValueError("豆包返回的字级时间超出音频范围")
            chars.extend((c, start, end) for c in clean(word["word"]))
    actual = "".join(c[0] for c in chars)
    if actual != clean(text):
        raise ValueError("字级时间戳与原口播不一致，保留原始结果等待核对，不用字数推算字幕")
    # 只在语义标点断字幕，不把字幕断行变成配音断句。
    cues = [x.strip() for x in re.findall(r"[^，。！？；\n]+[，。！？；]?", text) if x.strip()]
    result, cursor = [], 0
    for cue in cues:
        size = len(clean(cue))
        if not size:
            continue
        if size > 38:
            raise ValueError("字幕超过两行容量，需要按语义拆分")
        result.append({"start": round(chars[cursor][1], 3),
                       "end": round(chars[cursor + size - 1][2], 3), "text": cue})
        cursor += size
    return result


def request(action: str, payload: dict, key: str, resource: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}/{action}", data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "X-Api-Key": key,
                 "X-Api-Resource-Id": resource, "X-Api-Request-Id": str(uuid.uuid4())})
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # 不回显请求头、凭证或未知服务正文。
        raise RuntimeError(f"豆包 {action} HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(f"豆包 {action} 网络请求未确认；保留任务号，再次运行只查询") from None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--speaker", default=DEFAULT_SPEAKER)
    ap.add_argument("--resource", default="seed-tts-2.0")
    ap.add_argument("--rate", type=int, default=-4)
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    text = "\n".join(s.strip() for s in Path(args.script).read_text().splitlines()
                     if s.strip() and not s.lstrip().startswith("#"))
    params = {"text": text, "speaker": args.speaker,
              "audio_params": {"format": "mp3", "sample_rate": 48000,
                               "bit_rate": 160000, "speech_rate": args.rate,
                               "enable_timestamp": True}}
    config = {"resource_id": args.resource, "req_params": params}
    fingerprint = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    state_file = work / "tts_receipt.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state["input_sha256"] != fingerprint:
            raise SystemExit("配音输入已改变，请使用新版本目录，避免误用旧声音")
        if state["status"] == "complete":
            audio = work / "voice.mp3"
            if audio.exists() and media_duration(str(audio)) > 0 and (work / "timeline.json").exists():
                print(json.dumps({"status": "complete", "audio": str(audio), "reused": True}))
                return 0
    else:
        state = None
    key = load_env(Path(args.env)).get("VOLCENGINE_TTS_API_KEY")
    if not key:
        raise SystemExit("VOLCENGINE_TTS_API_KEY ABSENT；未发起合成")
    if state is None:
        task_id = str(uuid.uuid4())
        payload = {"user": {"uid": "cut-a-few-videos"}, "unique_id": task_id, "req_params": params}
        save(work / "tts_request.json", {"resource_id": args.resource, "body": payload})
        state = {"provider": "doubao", "task_id": task_id, "input_sha256": fingerprint,
                 "speaker": args.speaker, "resource_id": args.resource, "status": "submitting"}
        save(state_file, state)
        response = request("submit", payload, key, args.resource)
        save(work / "tts_submit.json", response)
        if response.get("code") != 20000000:
            state.update(status="submit_failed", code=response.get("code"))
            save(state_file, state)
            raise SystemExit(f"豆包合成提交失败，code={response.get('code')}")
        state.update(status="running", task_id=response.get("data", {}).get("task_id", task_id))
        save(state_file, state)
    if state["status"] == "submit_failed":
        raise SystemExit("上次提交失败；先核对回执，不自动重复付费请求")
    response = request("query", {"task_id": state["task_id"]}, key, args.resource)
    save(work / "tts_result.json", response)
    if response.get("code") != 20000000:
        raise SystemExit(f"查询尚未确认，code={response.get('code')}；保留原任务号")
    data = response.get("data", {})
    if data.get("task_status") == 1:
        print(json.dumps({"status": "running", "task_id": state["task_id"]}))
        return 3
    if data.get("task_status") != 2:
        state["status"] = "failed"
        save(state_file, state)
        raise SystemExit("豆包合成未成功，请核对 tts_result.json")
    audio = work / "voice.mp3"
    temp = work / "voice.download.mp3"
    with urllib.request.urlopen(data["audio_url"], timeout=60) as response, temp.open("wb") as f:
        while block := response.read(1 << 20):
            f.write(block)
    duration = media_duration(str(temp))
    timeline = subtitles(text, data.get("sentences", []), duration)
    if not timeline or timeline[-1]["end"] > duration + 0.1:
        raise SystemExit("字幕时序不完整")
    temp.replace(audio)
    save(work / "timeline.json", timeline)
    save(work / "subs.json", timeline)
    state.update(status="complete", audio=str(audio), duration=duration,
                 timestamps="provider_word_timestamps", subtitle_count=len(timeline))
    save(state_file, state)
    print(json.dumps({"status": "complete", "audio": str(audio), "duration": duration}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
