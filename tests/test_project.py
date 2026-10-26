"""通用输入与声音组合的离线行为检查。"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_video as B
import compose as C
from check_credentials import load_env
from minimax_video import load_key


class ProjectTests(unittest.TestCase):
    def setup_project(self, folder):
        from PIL import Image
        image = folder / "image.png"
        Image.new("RGB", (120, 120), "white").save(image)
        cfg = json.loads(Path("template/layout.json").read_text())
        for spec in cfg["fonts"].values():
            spec["path"] = "pillow-default"
        for name, data in [("layout", cfg), ("timeline", [
            {"start": 0.2, "end": 1.5, "text": "First scene."},
            {"start": 2.2, "end": 3.4, "text": "Last scene."}]),
            ("scenes", [{"anchor": None, "asset": str(image)},
                        {"anchor": "Last", "asset": str(image)}])]:
            (folder / f"{name}.json").write_text(json.dumps(data))
        (folder / "script.txt").write_text("First scene.\nLast scene.")
        return {"title": "Test", "footer": "", "duration": 4,
                **{k: str(folder / f"{k}.json") for k in ("layout", "timeline", "scenes")},
                "script": str(folder / "script.txt"), "voice": None, "music": None}

    def test_anchor_timing_and_ending(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = self.setup_project(folder)
            work = folder / "v1"
            work.mkdir()
            args = B.prepare(project, work, False, False)
            shots = json.loads((work / "shots.json").read_text())
            subs = json.loads((work / "subs.json").read_text())
            self.assertEqual(shots[1]["start"], 2.2)
            self.assertEqual(shots[-1]["end"], 4)
            self.assertEqual(subs[-1]["end"], 4)
            self.assertIsNone(args.audio)

    def test_missing_words_and_missing_anchors_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = self.setup_project(folder)
            (folder / "script.txt").write_text("First scene.\nA missing sentence.\nLast scene.")
            with self.assertRaisesRegex(ValueError, "完整覆盖"):
                B.prepare(project, folder, False, False)
            (folder / "script.txt").write_text("First scene.\nLast scene.")
            scenes = json.loads((folder / "scenes.json").read_text())
            scenes[1]["anchor"] = "Not present"
            (folder / "scenes.json").write_text(json.dumps(scenes))
            with self.assertRaisesRegex(ValueError, "唯一定位"):
                B.prepare(project, folder, False, False)

    def test_poster_hides_card_and_preserves_custom_shadow(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = self.setup_project(folder)
            project["band_art"] = str(folder / "image.png")
            layout_path = Path(project["layout"])
            cfg = json.loads(layout_path.read_text())
            # 白色细描边仍需深色投影；用户已选的另一套投影应保留。
            cfg["fonts"]["title"]["stroke_color"] = "#FFFFFF"
            custom = {"dx": 1, "dy": 4, "blur": 8, "opacity": 0.4, "color": "#234567"}
            cfg["fonts"]["quote"]["shadow"] = custom
            layout_path.write_text(json.dumps(cfg))
            work = folder / "v1"
            work.mkdir()
            B.prepare(project, work, False, False)
            output = json.loads((work / "layout.json").read_text())
            report = json.loads((work / "layout_report.json").read_text())
            self.assertTrue(output["bands"]["card"]["hidden"])
            self.assertEqual(output["text_slots"]["title"]["band"], "top")
            for name in ("top", "bottom"):
                self.assertEqual(output["bands"][name]["image"], project["band_art"])
                self.assertEqual(output["bands"][name]["image_anchor"], name)
            color = output["fonts"]["title"]["shadow"]["color"].lstrip("#")
            self.assertLess(max(int(color[i:i + 2], 16) for i in (0, 2, 4)), 128)
            self.assertEqual(output["fonts"]["quote"]["shadow"], custom)
            self.assertEqual(report["overflow"], [])

    def test_no_voice_preserves_duration_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = self.setup_project(folder)
            project.update(voice="mock-voice.mp3", tail=1.2)
            project.pop("duration")
            with patch.object(C, "media_duration", return_value=4.1):
                args = B.prepare(project, folder, True, True)
                self.assertIsNone(args.audio)
                self.assertAlmostEqual(args.duration, 5.3)
                project["duration"] = 3
                with self.assertRaises(ValueError):
                    B.prepare(project, folder, True, True)

    def test_credentials_do_not_fall_back_to_process_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "absent.env"
            with patch.dict(os.environ, {"MINIMAX_API_KEY": "MOCK_NOT_A_REAL_KEY"}):
                self.assertEqual(load_env(missing), {})
                with self.assertRaisesRegex(SystemExit, "ABSENT"):
                    load_key(str(missing))

    def test_four_audio_combinations_have_full_length(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "tone.wav"
            C.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                   "sine=frequency=220:sample_rate=48000:duration=2", str(source)], "测试声音")
            cfg = {"audio": {"lufs": -16}}
            for index, (voice, music) in enumerate([(True, True), (True, False), (False, True), (False, False)]):
                work = folder / str(index)
                work.mkdir()
                args = argparse.Namespace(audio=str(source) if voice else None,
                    music=str(source) if music else None, no_music=False, music_gain=-14)
                out = C.mix_soundtrack(args, cfg, 3, work)
                self.assertAlmostEqual(C.media_duration(str(out)), 3, places=2)
                info = C.probe(str(out))["streams"][0]
                self.assertEqual(info["channels"], 2)
                self.assertEqual(info["sample_rate"], "48000")
                raw = C.run(["ffmpeg", "-v", "error", "-i", str(out), "-af", "astats",
                             "-f", "null", "-"], "音轨解码")
            # --no-music 优先于给定的音乐路径，静音输出必须为全零采样。
            work = folder / "override"
            work.mkdir()
            args = argparse.Namespace(audio=None, music=str(source), no_music=True, music_gain=-14)
            out = C.mix_soundtrack(args, cfg, 3, work)
            import wave
            with wave.open(str(out), "rb") as audio:
                self.assertFalse(any(audio.readframes(audio.getnframes())))


if __name__ == "__main__":
    unittest.main()
