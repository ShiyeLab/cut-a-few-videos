#!/usr/bin/env python3
"""离线检查：转场不吞时长、转场帧确实混合、截短文件不能通过。"""
import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import compose as C
from doubao_tts import subtitles
from doubao_preview import make_payload, receive


class VideoFixes(unittest.TestCase):
    def test_static_push_moves_without_pixel_jumps(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            image = Image.new("RGB", (320, 340))
            ImageDraw.Draw(image).ellipse((68, 73, 92, 97), fill="white")
            source = folder / "marker.png"
            image.save(source)
            cfg = {"canvas": {"fps": 30}, "bands": {"center": {"w": 320, "h": 340}}}
            video = C.render_center([{"asset": str(source), "start": 0, "end": 3, "zoom": 0.06}],
                                    cfg, 3, folder, 0)
            raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(video),
                                           "-f", "rawvideo", "-pix_fmt", "gray", "-"])
            frame_size = 320 * 340
            self.assertEqual(len(raw), 90 * frame_size)
            centers = []
            for start in range(0, len(raw), frame_size):
                frame = raw[start:start + frame_size]
                mass = xsum = ysum = 0
                for y in range(50, 120):
                    for x in range(50, 110):
                        value = max(0, frame[y * 320 + x] - 16)
                        mass += value
                        xsum += x * value
                        ysum += y * value
                centers.append((xsum / mass, ysum / mass))
            for axis in (0, 1):
                self.assertLess(centers[-1][axis] - centers[0][axis], -3)
                jumps = [b[axis] - a[axis] for a, b in zip(centers, centers[1:])]
                self.assertLess(max(abs(step) for step in jumps), 0.45)
                self.assertLess(max(jumps), 0.15)

    def test_direction_is_separate_from_spoken_text(self):
        payload = make_payload("你好。", "mock-voice", "自然讲述", -4)["req_params"]
        self.assertEqual(payload["text"], "你好。")
        self.assertEqual(json.loads(payload["additions"])["context_texts"], ["自然讲述"])
        self.assertTrue(payload["audio_params"]["enable_subtitle"])
        self.assertNotIn("additions", make_payload("你好。", "mock-voice", None, -4)["req_params"])
        with self.assertRaises(ValueError):
            make_payload("字" * 301, "mock-voice", "自然讲述", -4)

    def test_stream_audio_assembly_and_provider_error(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "preview.mp3"
            events = [{"code": 0, "data": base64.b64encode(b"first").decode()},
                      {"code": 0, "data": base64.b64encode(b"second").decode()},
                      {"code": 20000000}]
            result, _ = receive(io.BytesIO("\n".join(json.dumps(e) for e in events).encode()), out)
            self.assertEqual(out.read_bytes(), b"firstsecond")
            self.assertTrue(result[-1]["explicit_end_marker"])
            with self.assertRaises(RuntimeError):
                receive(io.BytesIO(b'{"code": 45000001}\n'), out)

    def test_word_timestamps_preserve_text_and_reject_missing_words(self):
        sentence = [{"words": [{"word": "你好，", "startTime": 0.3, "endTime": 1.1},
                               {"word": "世界。", "startTime": 1.6, "endTime": 2.7}]}]
        result = subtitles("你好，世界。", sentence, 3)
        self.assertEqual([(x["start"], x["end"]) for x in result], [(0.3, 1.1), (1.6, 2.7)])
        with self.assertRaises(ValueError):
            subtitles("你好，完整的世界。", sentence, 3)

    def test_transition_keeps_full_duration_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for color in ["red", "blue"]:
                C.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                       f"color={color}:s=320x340:r=30:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       str(folder / f"{color}.mp4")], "测试素材")
            shots = [{"asset": str(folder / "red.mp4"), "start": 0, "end": 3},
                     {"asset": str(folder / "blue.mp4"), "start": 3, "end": 6}]
            cfg = {"canvas": {"fps": 30}, "bands": {"center": {"w": 320, "h": 340}}}
            center = C.render_center(shots, cfg, 6, folder, 0.4)
            self.assertAlmostEqual(C.media_duration(str(center)), 6, places=2)
            pixel = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "3.2", "-i", str(center),
                                             "-frames:v", "1", "-vf", "scale=1:1", "-pix_fmt", "rgb24",
                                             "-f", "rawvideo", "-"])
            self.assertGreater(pixel[0], 40)
            self.assertGreater(pixel[2], 40)
            truncated = folder / "truncated.mp4"
            C.run(["ffmpeg", "-v", "error", "-y", "-i", str(center), "-f", "lavfi", "-i",
                   "sine=frequency=440:sample_rate=48000:duration=4", "-t", "4", "-c:v", "copy",
                   "-c:a", "aac", str(truncated)], "截短回归样例")
            report = C.verify(str(truncated), None, None, 6)
            self.assertTrue(report["decode_ok"])
            self.assertFalse(report["duration_ok"])


if __name__ == "__main__":
    unittest.main()
