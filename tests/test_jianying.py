"""剪映测试草稿的工程身份与 Mac 首页登记。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import jianying_smoke as smoke


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
        running = patch.object(smoke, "app_running", return_value=False)
        running.start()
        self.addCleanup(running.stop)

    def make_draft(self, name):
        script = smoke.draft.DraftFolder(str(self.root)).create_draft(name, 1080, 1920)
        track, = script.append_tracks([smoke.TrackSpec(smoke.TrackType.text, "标题")])
        script.add_segment(smoke.draft.TextSegment("可编辑标题", smoke.trange("0s", "6s")), track)
        return smoke.save_draft(script, self.root / name, str(uuid.uuid4()).upper(), name)

    def test_unique_identity_matches_in_both_content_files_and_metadata(self):
        entries = [self.make_draft("first"), self.make_draft("second")]
        self.assertNotEqual(entries[0]["draft_id"], entries[1]["draft_id"])
        for entry in entries:
            folder = Path(entry["draft_fold_path"])
            for filename in ("draft_content.json", "draft_info.json"):
                content = json.loads((folder / filename).read_text())
                self.assertEqual(content["id"], entry["draft_id"])
                self.assertEqual(content["name"], entry["draft_name"])
                self.assertEqual(content["duration"], entry["tm_duration"])
            self.assertEqual(json.loads((folder / "draft_meta_info.json").read_text()), entry)
            self.assertEqual(entry["draft_json_file"], str(folder / "draft_info.json"))

    def test_registration_keeps_existing_entries_and_original_backup(self):
        entry = self.make_draft("new")
        backup = smoke.register_draft(self.root, entry, smoke.read_index(self.root))
        updated = json.loads(self.index.read_text())
        self.assertEqual(updated["all_draft_store"], [entry, self.existing])
        self.assertEqual(updated["draft_ids"], 2)
        self.assertEqual(updated["extra"], "preserve")
        self.assertEqual(backup.read_bytes(), self.original)
        with self.assertRaisesRegex(ValueError, "相同工程 ID"):
            smoke.register_draft(self.root, entry, self.index.read_bytes())

    def test_concurrent_index_change_is_not_overwritten(self):
        entry = self.make_draft("new")
        changed = self.original + b"\n"
        self.index.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "发生变化"):
            smoke.register_draft(self.root, entry, self.original)
        self.assertEqual(self.index.read_bytes(), changed)

    def test_running_app_prevents_index_writes(self):
        entry = self.make_draft("new")
        with patch.object(smoke, "app_running", return_value=True):
            with self.assertRaisesRegex(ValueError, "退出剪映"):
                smoke.read_index(self.root)
            with self.assertRaisesRegex(ValueError, "发生变化"):
                smoke.register_draft(self.root, entry, self.original)
        self.assertEqual(self.index.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
