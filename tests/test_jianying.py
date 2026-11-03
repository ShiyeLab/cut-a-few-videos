"""剪映草稿：工程身份、Mac 首页登记，以及从合成产物转换的轨道与时间。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_video as B
import jianying_draft as J


class DraftRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.index = self.root / "root_meta_info.json"
        self.existing = {"draft_id": "existing-project", "draft_name": "已有草稿"}
        self.original = json.dumps({"all_draft_store": [self.existing], "draft_ids": 1,
                                    "root_path": str(self.root), "extra": "preserve"}).encode()
        self.index.write_bytes(self.original)
        running = patch.object(J, "app_running", return_value=False)
        running.start()
        self.addCleanup(running.stop)

    def make_draft(self, name):
        script = J.draft.DraftFolder(str(self.root)).create_draft(name, 1080, 1920)
        track, = script.append_tracks([J.TrackSpec(J.TrackType.text, "标题")])
        script.add_segment(J.draft.TextSegment("可编辑标题", J.span(0, 6)), track)
        return J.save_draft(script, self.root / name, str(uuid.uuid4()).upper(), name)

    def test_unique_identity_matches_in_both_content_files_and_metadata(self):
        entries = [self.make_draft("first"), self.make_draft("second")]
        self.assertNotEqual(entries[0]["draft_id"], entries[1]["draft_id"])
        for entry in entries:
            folder = Path(entry["draft_fold_path"])
            for filename in ("draft_content.json", "draft_info.json"):
                content = json.loads((folder / filename).read_text(encoding="utf-8"))
                self.assertEqual(content["id"], entry["draft_id"])
                self.assertEqual(content["name"], entry["draft_name"])
                self.assertEqual(content["duration"], entry["tm_duration"])
            self.assertEqual(json.loads((folder / "draft_meta_info.json").read_text(encoding="utf-8")), entry)
            self.assertEqual(entry["draft_json_file"], str(folder / "draft_info.json"))

    def test_registration_keeps_existing_entries_and_original_backup(self):
        entry = self.make_draft("new")
        backup = J.register_draft(self.root, entry, J.read_index(self.root))
        updated = json.loads(self.index.read_text(encoding="utf-8"))
        self.assertEqual(updated["all_draft_store"], [entry, self.existing])
        self.assertEqual(updated["draft_ids"], 2)
        self.assertEqual(updated["extra"], "preserve")
        self.assertEqual(backup.read_bytes(), self.original)
        with self.assertRaisesRegex(ValueError, "相同工程 ID"):
            J.register_draft(self.root, entry, self.index.read_bytes())

    def test_concurrent_index_change_is_not_overwritten(self):
        entry = self.make_draft("new")
        changed = self.original + b"\n"
        self.index.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "发生变化"):
            J.register_draft(self.root, entry, self.original)
        self.assertEqual(self.index.read_bytes(), changed)

    def test_running_app_prevents_index_writes(self):
        entry = self.make_draft("new")
        with patch.object(J, "app_running", return_value=True):
            with self.assertRaisesRegex(ValueError, "退出剪映"):
                J.read_index(self.root)
            with self.assertRaisesRegex(ValueError, "发生变化"):
                J.register_draft(self.root, entry, self.original)
        self.assertEqual(self.index.read_bytes(), self.original)


class DraftConversionTests(unittest.TestCase):
    def test_cover_fills_center_window_and_focus_moves_frame(self):
        win = {"x": 0, "y": 380, "w": 1080, "h": 1150}
        middle = J.place(540, 960, (1080, 1920), win, "cover", 0.5)
        self.assertAlmostEqual(middle.scale_x, 1.0)
        self.assertAlmostEqual(middle.transform_y, (960 - 955) / 960)
        top = J.place(540, 960, (1080, 1920), win, "cover", 0)
        self.assertAlmostEqual(top.transform_y, (960 - 955 - 385) / 960)
        square = J.place(768, 768, (1080, 1920), win, "cover", 0.5)
        self.assertAlmostEqual(square.scale_x, 1150 / 1080)
        self.assertAlmostEqual(J.place(768, 768, (1080, 1920), win, "contain", 0.5).scale_x, 1.0)

    def make_work(self, folder):
        from PIL import Image
        Image.new("RGB", (120, 120), "white").save(folder / "image.png")
        cfg = json.loads(Path("template/layout.json").read_text(encoding="utf-8"))
        for spec in cfg["fonts"].values():
            spec["path"] = "pillow-default"
        timeline = [{"start": 0.2, "end": 1.5, "text": "Only scene."}]
        for name, data in (("layout", cfg), ("timeline", timeline),
                           ("scenes", [{"anchor": None, "asset": str(folder / "image.png")}])):
            (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        (folder / "script.txt").write_text("Only scene.", encoding="utf-8")
        project = {"title": "Test", "footer": "", "duration": 2, "voice": None, "music": None,
                   "script": str(folder / "script.txt"),
                   **{k: str(folder / f"{k}.json") for k in ("layout", "timeline", "scenes")}}
        work = folder / "v1"
        work.mkdir()
        B.prepare(project, work, True, True)
        return work

    def test_open_app_defers_registration_until_register(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp).resolve()
            work = self.make_work(folder)
            root = folder / "drafts"
            root.mkdir()
            index = root / "root_meta_info.json"
            original = json.dumps({"all_draft_store": [], "draft_ids": 0}).encode()
            index.write_bytes(original)
            with patch.object(J, "app_running", return_value=True):
                message = J.export(work, root)
            self.assertIn("--register", message)
            self.assertEqual(index.read_bytes(), original)
            with patch.object(J, "app_running", return_value=False):
                names = J.register_pending(root)
                self.assertEqual(len(names), 1)
                self.assertEqual([e["draft_name"] for e in json.loads(index.read_text())["all_draft_store"]], names)
                self.assertEqual(J.register_pending(root), [])
                self.assertIn("登记剪映首页", J.export(work, root))
            self.assertEqual(len(json.loads(index.read_text())["all_draft_store"]), 2)

    def test_tracks_follow_the_same_timeline_as_the_video(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            Image.new("RGB", (120, 120), "white").save(folder / "image.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=540x960:rate=30:duration=4", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(folder / "clip.mp4")], check=True)
            cfg = json.loads(Path("template/layout.json").read_text(encoding="utf-8"))
            for spec in cfg["fonts"].values():
                spec["path"] = "pillow-default"
            timeline = [{"start": 0.2, "end": 1.5, "text": "First scene."},
                        {"start": 2.2, "end": 3.4, "text": "Last scene."}]
            scenes = [{"anchor": None, "asset": str(folder / "image.png"), "move": "push"},
                      {"anchor": "Last", "asset": str(folder / "clip.mp4"), "in": 0.5, "focus_y": 0.3}]
            for name, data in (("layout", cfg), ("timeline", timeline), ("scenes", scenes)):
                (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            (folder / "script.txt").write_text("First scene.\nLast scene.", encoding="utf-8")
            project = {"title": "Test", "footer": "Footer", "duration": 4, "voice": None, "music": None,
                       "script": str(folder / "script.txt"),
                       **{k: str(folder / f"{k}.json") for k in ("layout", "timeline", "scenes")}}
            work = folder / "v1"
            work.mkdir()
            B.prepare(project, work, True, True)
            root = folder / "drafts"
            root.mkdir()
            draft_folder = J.build(work, root, "test-draft", "TEST-ID")

            content = json.loads((draft_folder / "draft_info.json").read_text(encoding="utf-8"))
            self.assertEqual(content["duration"], 4_000_000)
            tracks = {t["name"]: t["segments"] for t in content["tracks"]}
            self.assertEqual([t["name"] for t in content["tracks"]][:2], ["中央窗", "底图"])
            window = tracks["中央窗"]
            self.assertEqual([s["target_timerange"] for s in window],
                             [{"start": 0, "duration": 2_200_000}, {"start": 2_200_000, "duration": 1_800_000}])
            self.assertEqual(window[1]["source_timerange"], {"start": 500_000, "duration": 1_800_000})
            texts = {m["id"]: json.loads(m["content"])["text"] for m in content["materials"]["texts"]}
            subs = json.loads((work / "subs.json").read_text(encoding="utf-8"))
            self.assertEqual([texts[s["material_id"]].replace("\n", "") for s in tracks["字幕"]],
                             [s["text"] for s in subs])
            self.assertEqual([texts[s["material_id"]] for s in tracks["标题"] + tracks["底部文字"]],
                             ["Test", "Footer"])
            for material in content["materials"]["videos"]:
                self.assertEqual(Path(material["path"]).parent, draft_folder / "media")


if __name__ == "__main__":
    unittest.main()
