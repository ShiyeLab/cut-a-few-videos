#!/usr/bin/env python3
"""离线检查：转场不吞时长、转场帧确实混合、截短文件不能通过。"""
import base64
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFilter, ImageStat

import compose as C
import doubao_tts_stream as T
from doubao_tts import subtitles
from doubao_preview import make_payload, receive

W, H, FPS = 320, 340, 30
CFG = {"canvas": {"fps": FPS}, "bands": {"center": {"w": W, "h": H}},
       "editing": {"move_rate": 0.05}}


def gray_frames(video: Path) -> list[bytes]:
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(video),
                                   "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    return [raw[i:i + W * H] for i in range(0, len(raw), W * H)]


def centroid(frame: bytes, box: tuple[int, int, int, int]) -> tuple[float, float]:
    x0, y0, x1, y1 = box
    mass = xsum = ysum = 0
    for y in range(y0, y1):
        row = frame[y * W:(y + 1) * W]
        for x in range(x0, x1):
            value = max(0, row[x] - 40)
            mass += value
            xsum += x * value
            ysum += y * value
    return xsum / mass, ysum / mass


class VideoFixes(unittest.TestCase):
    def test_moves_are_uniform_without_stutter(self):
        # 柔边光点的质心可测到亚像素位移；逐帧速度须稳定，前后段速度一致（匀速）。
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            image = Image.new("L", (W, H), 30)
            ImageDraw.Draw(image).ellipse((250, 260, 270, 280), fill=255)
            source = folder / "marker.png"
            image.filter(ImageFilter.GaussianBlur(4)).convert("RGB").save(source)
            for move, axis in [("push", 0), ("pull", 0), ("pan_left", 0), ("pan_up", 1)]:
                work = folder / move
                work.mkdir()
                video = C.render_center([{"asset": str(source), "start": 0, "end": 3, "move": move}],
                                        CFG, 3, work, 0)
                frames = gray_frames(video)
                self.assertEqual(len(frames), 90)
                track = []
                for frame in frames:
                    point = track[-1] if track else centroid(frame, (170, 170, W, H))
                    for _ in range(2):  # 先粗定位再精算，避免框住半个光点
                        x, y = int(point[0]), int(point[1])
                        point = centroid(frame, (x - 22, y - 22, x + 22, y + 22))
                    track.append(point)
                steps = [b[axis] - a[axis] for a, b in zip(track, track[1:])]
                mean = sum(steps) / len(steps)
                self.assertGreater(abs(mean), 0.1, move)
                ratios = [s / mean for s in steps]
                self.assertGreater(min(ratios), 0.5, (move, ratios))
                self.assertLess(max(ratios), 1.5, (move, ratios))
                third = len(steps) // 3
                early, late = sum(steps[:third]) / third, sum(steps[-third:]) / third
                self.assertLess(abs(early / late - 1), 0.12, (move, early, late))

    def test_final_video_keeps_slow_push_smooth(self):
        # 默认速度下每帧只移动约 0.1 像素；有损编码常把这种位移跳过成停顿，须检查最终成片。
        import argparse
        import layout as L
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cfg = json.loads(Path("template/layout.json").read_text(encoding="utf-8"))
            for spec in cfg["fonts"].values():
                spec["path"] = "pillow-default"
            (folder / "layout.json").write_text(json.dumps(cfg), encoding="utf-8")
            # 暗部纹理：足以让编码器按真实照片的方式分配码率，又不进入光点的测量阈值。
            texture = Image.effect_noise((270, 288), 40).resize((1080, 1150), Image.BICUBIC).point(
                lambda v: 50 + (v - 128) * 0.4)
            blob = Image.new("L", (1080, 1150), 0)
            ImageDraw.Draw(blob).ellipse((990, 565, 1010, 585), fill=255)
            Image.composite(Image.new("L", (1080, 1150), 255), texture,
                            blob.filter(ImageFilter.GaussianBlur(4))).convert("RGB").save(folder / "page.png")
            L.render_card(cfg, "", "")[0].save(folder / "card.png")
            (folder / "shots.json").write_text(json.dumps(
                [{"asset": str(folder / "page.png"), "end": 3, "move": "push"}]), encoding="utf-8")
            C.compose(argparse.Namespace(config=str(folder / "layout.json"), card=str(folder / "card.png"),
                shots=str(folder / "shots.json"), subs=None, audio=None, music=None, no_music=True,
                music_gain=-14, duration=3, transition=0, out=str(folder / "out.mp4"), work=str(folder)))
            # 只取光点附近 120×120 区域，光点在成片中位于 x≈1000、y≈380+575。
            raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(folder / "out.mp4"),
                                           "-vf", "crop=120:120:940:895", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
            xs = []
            for i in range(0, len(raw), 120 * 120):
                frame = raw[i:i + 120 * 120]
                mass = xsum = 0
                for y in range(30, 90):
                    for x in range(120):
                        value = max(0, frame[y * 120 + x] - 110)
                        mass += value
                        xsum += x * value
                xs.append(xsum / mass)
            steps = [b - a for a, b in zip(xs, xs[1:])]
            mean = sum(steps) / len(steps)
            self.assertGreater(mean, 0.05)
            self.assertEqual([round(s / mean, 2) for s in steps if s / mean < 0.4], [])

    def test_transitions_start_and_stop_smoothly(self):
        # 逐帧变化量不得突跳：内置闪白开头两帧跳变、内置滑入首帧即全速，均不允许。
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # 非周期渐变：位移量与帧差成正比，避免条纹相位造成的测量混叠。
            for name, color in [("a", (200, 60, 50)), ("b", (40, 80, 170))]:
                image = Image.new("RGB", (W, H))
                draw = ImageDraw.Draw(image)
                for x in range(W):
                    k = 0.35 + 0.65 * x / W
                    draw.line((x, 0, x, H), fill=tuple(int(c * k) for c in color))
                image.save(folder / f"{name}.png")
            for name in C.TRANSITIONS:
                work = folder / name
                work.mkdir()
                shots = [{"asset": str(folder / "a.png"), "start": 0, "end": 1},
                         {"asset": str(folder / "b.png"), "start": 1, "end": 2, "transition": name}]
                frames = gray_frames(C.render_center(shots, CFG, 2, work, 0.5))
                change = [sum(abs(p - q) for p, q in zip(a[::7], b[::7])) / len(a[::7])
                          for a, b in zip(frames[26:50], frames[27:51])]
                self.assertLess(change[0], 1, name)  # 转场前静止
                self.assertLess(change[-1], 1, name)  # 转场后静止
                if name == "fade":
                    continue  # 线性叠化：亮度匀速变化
                peak = max(change)
                jolts = [abs(b - a) / peak for a, b in zip(change, change[1:])]
                self.assertLess(max(jolts), 0.6, (name, [round(c, 1) for c in change]))

    def test_slow_motion_needs_high_frame_rate_source(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for rate in (30, 60):
                C.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                       f"testsrc2=size={W}x{H}:rate={rate}:duration=3", "-c:v", "libx264",
                       "-pix_fmt", "yuv420p", str(folder / f"r{rate}.mp4")], "测试素材")
            shot = {"start": 0, "end": 2, "speed": 0.5}
            with self.assertRaisesRegex(SystemExit, "慢放"):
                C.render_center([{**shot, "asset": str(folder / "r30.mp4")}], CFG, 2, folder, 0)
            frames = gray_frames(C.render_center([{**shot, "asset": str(folder / "r60.mp4")}],
                                                 CFG, 2, folder, 0))
            repeats = sum(a == b for a, b in zip(frames, frames[1:]))
            self.assertEqual(repeats, 0)

    def test_unknown_move_or_transition_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a.png"
            Image.new("RGB", (W, H)).save(source)
            for shot, message in [({"zoom": 0.03}, "不支持 zoom"), ({"move": "spin"}, "move"),
                                  ({"focus_y": 2}, "focus_y")]:
                shots_file = Path(directory) / "shots.json"
                shots_file.write_text(json.dumps([{"asset": str(source), "end": 2, **shot}]), encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, message):
                    C.load_shots(type("Args", (), {"shots": str(shots_file)}), 2)
            shots_file.write_text(json.dumps([{"asset": str(source), "end": 1},
                                              {"asset": str(source), "start": 1, "end": 2,
                                               "transition": "zoomin"}]), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "transition"):
                C.load_shots(type("Args", (), {"shots": str(shots_file)}), 2)

    def test_blur_background_is_equally_soft_with_move(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            image = Image.new("RGB", (480, 180), "white")
            draw = ImageDraw.Draw(image)
            for x in range(0, 480, 12):
                draw.rectangle((x, 0, x + 5, 180), fill="black")
            source = folder / "stripes.png"
            image.save(source)
            cfg = {"canvas": {"fps": 30}, "bands": {"center": {"w": 320, "h": 340}}}
            spread = []
            for move in (None, "push"):
                work = folder / f"move-{move}"
                work.mkdir()
                video = C.render_center([{"asset": str(source), "start": 0, "end": 1,
                                          "fit": "blur", "move": move}], cfg, 1, work, 0)
                raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1",
                                               "-f", "rawvideo", "-pix_fmt", "gray", "-"])
                # 只看前景上方的虚化背景区。
                band = Image.frombytes("L", (320, 340), raw).crop((0, 0, 320, 80))
                spread.append(ImageStat.Stat(band).stddev[0])
            self.assertLess(abs(spread[1] - spread[0]), 6, spread)

    def test_stream_provider_error_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "script.txt").write_text("你好。", encoding="utf-8")
            (folder / "env").write_text("VOLCENGINE_TTS_API_KEY=MOCK_NOT_A_REAL_KEY\n", encoding="utf-8")
            argv = ["doubao_tts_stream.py", "--script", str(folder / "script.txt"), "--work",
                    str(folder / "voice"), "--speaker", "mock-voice", "--env", str(folder / "env")]
            response = io.BytesIO(b'{"code": 45000001}\n')
            with patch.object(sys, "argv", argv), \
                    patch.object(T.urllib.request, "urlopen", return_value=response) as send:
                with self.assertRaisesRegex(SystemExit, "45000001"):
                    T.main()
                state = json.loads((folder / "voice" / "tts_receipt.json").read_text(encoding="utf-8"))
                self.assertEqual(state["status"], "provider_failed")
                self.assertIn("45000001", state["error"])
                with self.assertRaisesRegex(SystemExit, "provider_failed"):
                    T.main()
                self.assertEqual(send.call_count, 1)

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
