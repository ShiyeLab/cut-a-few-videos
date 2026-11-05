"""通用输入与声音组合的离线行为检查。"""
import argparse
import copy
from contextlib import redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_video as B
import compose as C
import minimax_video as M
import stock_search as P
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

    def test_interrupted_video_submission_is_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            spec = folder / "spec.json"
            spec.write_text(json.dumps({"items": [{"slug": "window", "prompt": "无字空镜"}]}), encoding="utf-8")
            (folder / "env").write_text("MINIMAX_API_KEY=MOCK_NOT_A_REAL_KEY\n", encoding="utf-8")
            argv = ["minimax_video.py", "--spec", str(spec), "--env", str(folder / "env"),
                    "--out", str(folder / "ai")]
            with patch.object(sys, "argv", argv), \
                    patch.object(M.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")) as send:
                with self.assertRaisesRegex(SystemExit, "结果未知"):
                    M.main()
                receipt = json.loads((folder / "ai" / "window" / "receipt.json").read_text(encoding="utf-8"))
                self.assertEqual(receipt["status"], "outcome_unknown")
                with self.assertRaisesRegex(SystemExit, "结果未知"):
                    M.main()
                self.assertEqual(send.call_count, 1)

    def test_expired_video_task_stops_polling(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "receipt.json").write_text(json.dumps({"status": "queued", "task_id": "mock-1"}),
                                                 encoding="utf-8")
            with patch.object(M, "call", return_value=(200, {"task": {"status": "expired"}})) as query, \
                    patch.object(M.time, "sleep") as wait:
                self.assertEqual(M.poll(folder, "MOCK_NOT_A_REAL_KEY")["status"], "expired")
                self.assertEqual(query.call_count, 1)
                wait.assert_not_called()

    def test_stock_prefers_files_wide_enough_for_center_window(self):
        files = [{"file_type": "video/mp4", "width": w, "height": h}
                 for w, h in [(540, 960), (720, 1280), (1080, 1920), (2160, 3840)]]
        self.assertEqual(P.pick_file({"video_files": files})["width"], 1080)
        self.assertEqual(P.pick_file({"video_files": files[:2]})["width"], 720)

    def test_stock_needs_get_separate_folders(self):
        self.assertNotEqual(P.slug("安静窗户"), P.slug("办公室打字"))
        self.assertEqual(P.slug("quiet window!"), "quiet-window")
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            brief = folder / "brief.json"
            brief.write_text(json.dumps({"shots": [
                {"type": "stock", "need": "窗边 光线", "query": "a"},
                {"type": "stock", "need": "窗边-光线", "query": "b"}]}), encoding="utf-8")
            (folder / "env").write_text("PEXELS_API_KEY=MOCK_NOT_A_REAL_KEY\n", encoding="utf-8")
            argv = ["stock_search.py", "--brief", str(brief), "--env", str(folder / "env"),
                    "--out", str(folder / "stock")]
            with patch.object(sys, "argv", argv), patch.object(P, "api_get") as search:
                self.assertEqual(P.main(), 2)
                search.assert_not_called()

    def test_pixabay_search_download_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sample.mp4"
            C.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:d=2",
                   "-c:v", "libx264", str(source)], "生成测试视频")
            brief = root / "brief.json"
            brief.write_text(json.dumps({"shots": [
                {"type": "stock", "need": "street", "query": "街道", "lang": "zh"}]}))
            config = root / "env"
            config.write_text("PIXABAY_API_KEY=MOCK_NOT_A_REAL_KEY\n")
            hit = {"id": 123, "pageURL": "https://example.invalid/123", "user": "test", "isAiGenerated": False,
                   "duration": 2, "videos": {"small": {
                       "url": source.as_uri(), "width": 64, "height": 64}}}
            argv = ["stock_search.py", "--env", str(config), "--brief", str(brief),
                    "--out", "projects/test", "--per-shot", "1"]
            with patch.object(P, "ROOT", root), patch.object(sys, "argv", argv), \
                    patch.object(P, "api_get", return_value={"hits": [dict(hit, id=124, isAiGenerated=True),
                                                                      hit]}) as search:
                self.assertEqual(P.main(), 0)
                self.assertEqual(P.main(), 0)
                search.assert_called_once()
                request = search.call_args.args[0]
                self.assertEqual(request.get_header("Accept"), "application/json")
                self.assertEqual(request.get_header("User-agent"), "cut-a-few-videos/1.0")
                url = P.urllib.parse.urlparse(request.full_url)
                self.assertEqual((url.hostname, url.path), ("pixabay.com", "/api/videos/"))
                params = P.urllib.parse.parse_qs(url.query)
                self.assertEqual((params["q"], params["lang"], params["per_page"]),
                                 (["街道"], ["zh"], ["3"]))
            folder = root / "projects/test/street"
            items = json.loads((folder / "manifest.json").read_text())["candidates"]
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item["id"], 123)
            self.assertIs(item["is_ai_generated"], False)
            self.assertEqual(item["page"], hit["pageURL"])
            self.assertEqual(item["license"], P.LICENSES["pixabay"])
            self.assertEqual((root / item["file"]).read_bytes(), source.read_bytes())
            self.assertTrue((root / item["still"]).is_file())
            for record in root.rglob("*.json"):
                self.assertNotIn("MOCK_NOT_A_REAL_KEY", record.read_text())

    def test_pixabay_http_error_keeps_key_out_of_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "env").write_text("PIXABAY_API_KEY=MOCK_NOT_A_REAL_KEY\n")
            (root / "brief").write_text(json.dumps({"shots": [
                {"type": "stock", "need": "walk", "query": "walking"}]}))
            argv = ["stock_search.py", "--provider", "pixabay", "--env", str(root / "env"),
                    "--brief", str(root / "brief")]
            err = urllib.error.HTTPError("https://example.invalid/?key=MOCK_NOT_A_REAL_KEY",
                                         429, "limit", {}, None)
            log = StringIO()
            with patch.object(P, "ROOT", root), patch.object(sys, "argv", argv), \
                    patch.object(P, "api_get", side_effect=err), redirect_stderr(log):
                self.assertEqual(P.main(), 1)
            self.assertIn("429", log.getvalue())
            self.assertNotIn("MOCK_NOT_A_REAL_KEY", log.getvalue())

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
