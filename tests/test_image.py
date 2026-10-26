"""生图请求、结果复用与中断保护的离线检查。"""
import base64
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import seedream_image as S


class ImageTests(unittest.TestCase):
    def test_image_saved_and_reused_without_resubmission(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "poster-v1"
            image = BytesIO()
            Image.new("RGB", (18, 32), "blue").save(image, format="PNG")
            response = BytesIO(json.dumps({"data": [{"b64_json":
                base64.b64encode(image.getvalue()).decode()}]}).encode())
            payload = {"prompt": "无字水彩", "model": S.MODEL}
            with patch.object(S.urllib.request, "urlopen", return_value=response) as send:
                output = S.generate(payload, work, "MOCK_NOT_A_REAL_KEY")
                self.assertEqual(json.loads(send.call_args.args[0].data), payload)
                self.assertEqual(S.generate(payload, work, None), output)
                self.assertEqual(send.call_count, 1)
                with self.assertRaisesRegex(ValueError, "输入已改变"):
                    S.generate({**payload, "prompt": "changed"}, work, None)
                self.assertEqual(send.call_count, 1)
            with Image.open(output) as picture:
                self.assertEqual(picture.size, (18, 32))
            receipt = json.loads((work / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "complete")
            for name in ("request.json", "receipt.json"):
                self.assertNotIn("MOCK_NOT_A_REAL_KEY", (work / name).read_text())

    def test_timeout_is_unknown_and_never_automatically_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "poster-v1"
            with patch.object(S.urllib.request, "urlopen", side_effect=TimeoutError("private detail")) as send:
                with self.assertRaisesRegex(ValueError, "结果未知") as error:
                    S.generate({"prompt": "test"}, work, "MOCK_NOT_A_REAL_KEY")
                self.assertNotIn("private detail", str(error.exception))
                self.assertEqual(json.loads((work / "receipt.json").read_text())["status"], "outcome_unknown")
                with self.assertRaisesRegex(ValueError, "已有未完成请求"):
                    S.generate({"prompt": "test"}, work, "MOCK_NOT_A_REAL_KEY")
                self.assertEqual(send.call_count, 1)

    def test_invalid_image_blocks_resubmission(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "poster-v1"
            response = BytesIO(b'{"data": [{"b64_json": "bm90IGFuIGltYWdl"}]}')
            with patch.object(S.urllib.request, "urlopen", return_value=response) as send:
                with self.assertRaisesRegex(ValueError, "没有一张可用图片"):
                    S.generate({"prompt": "test"}, work, "MOCK_NOT_A_REAL_KEY")
                self.assertFalse((work / "poster.png").exists())
                self.assertEqual(json.loads((work / "receipt.json").read_text())["status"], "invalid_image")
                with self.assertRaisesRegex(ValueError, "已有未完成请求"):
                    S.generate({"prompt": "test"}, work, "MOCK_NOT_A_REAL_KEY")
                self.assertEqual(send.call_count, 1)

    def test_dry_run_needs_no_key_or_network(self):
        with tempfile.TemporaryDirectory() as temp:
            prompt = Path(temp) / "prompt.txt"
            prompt.write_text("No text, soft watercolor.")
            work = Path(temp) / "poster-v1"
            with patch.object(sys, "argv", ["seedream_image.py", "--prompt", str(prompt),
                    "--work", str(work), "--dry-run"]), patch.object(S, "load_env") as env, \
                    patch.object(S.urllib.request, "urlopen") as send, redirect_stdout(StringIO()) as out:
                S.main()
                env.assert_not_called()
                send.assert_not_called()
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["response_format"], "b64_json")
                self.assertNotIn("sequential_image_generation", payload)
                self.assertNotIn("stream", payload)
                self.assertFalse(work.exists())


if __name__ == "__main__":
    unittest.main()
