"""MediaKit 任务生命周期与配置隔离；不发起在线请求。"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import understand_video as U


class UnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = self.root / ".env.local"
        self.env.write_text("MEDIAKIT_API_KEY=MOCK_NOT_A_REAL_KEY\n")
        self.video = self.root / "source with spaces.mp4"
        self.video.write_bytes(b"offline input")
        self.request = U.request_for([str(self.video)], "理解真实动作与可用区间", "Quality")
        self.work = self.root / "understanding"
        cli = patch.object(U.shutil, "which", return_value="/mock/mediakit-cli")
        cli.start()
        self.addCleanup(cli.stop)

    def run_job(self, request=True):
        return U.run(self.request if request else None, self.work, self.env, "mediakit-cli")

    def test_submit_poll_complete_and_reuse_without_new_task(self):
        responses = [{"task_id": "mock-task-1"}, {"task_id": "mock-task-1", "status": "running"},
                     {"task_id": "mock-task-1", "status": "completed", "contents": ["实际画面与候选区间"]}]
        with patch.object(U, "call_cli", side_effect=responses) as call:
            self.assertEqual(self.run_job(), "queued")
            self.assertEqual(self.run_job(False), "running")
            self.assertEqual(self.run_job(), "completed")
            self.env.unlink()
            self.assertEqual(self.run_job(False), "completed")
            self.assertEqual(call.call_count, 3)
            submit = call.call_args_list[0].args[1]
            self.assertEqual(submit[:2], ["video", "video-understand-router"])
            self.assertEqual(submit[submit.index("--video-urls") + 1], str(self.video.resolve()))
            self.assertEqual(submit[submit.index("--scene") + 1], "editing")
            for args in call.call_args_list[1:]:
                self.assertEqual(args.args[1], ["shared", "query-task", "--task-id", "mock-task-1"])
        self.assertIn("候选区间", (self.work / "analysis.md").read_text())
        for path in self.work.iterdir():
            self.assertNotIn("MOCK_NOT_A_REAL_KEY", path.read_text())

    def test_unknown_submit_is_never_automatically_retried(self):
        with patch.object(U, "call_cli", side_effect=ValueError("中断")) as call:
            with self.assertRaises(ValueError):
                self.run_job()
            with self.assertRaisesRegex(ValueError, "结果未知"):
                self.run_job()
            self.assertEqual(call.call_count, 1)
        self.assertEqual(json.loads((self.work / "receipt.json").read_text())["status"], "outcome_unknown")

    def test_query_failure_resumes_original_task_and_failed_task_stops(self):
        responses = [{"task_id": "mock-task-1"}, ValueError("查询中断"),
                     {"task_id": "mock-task-1", "status": "failed"}]
        with patch.object(U, "call_cli", side_effect=responses) as call:
            self.run_job()
            with self.assertRaises(ValueError):
                self.run_job(False)
            with self.assertRaisesRegex(ValueError, "失败或取消"):
                self.run_job(False)
            with self.assertRaisesRegex(ValueError, "失败或取消"):
                self.run_job()
            self.assertEqual(call.call_count, 3)
            self.assertEqual(call.call_args.args[1][-1], "mock-task-1")

    def cli_outputs(self, *outputs):
        # 按 CLI 约定模拟：失败时退出码 1，并在标准输出给出带 success=false 的 JSON。
        return [subprocess.CompletedProcess([], code, json.dumps(body, ensure_ascii=False), "")
                for code, body in outputs]

    def test_failed_task_reported_by_cli_exit_code_is_recorded(self):
        outputs = self.cli_outputs(
            (0, {"task_id": "mock-task-1"}),
            (1, {"task_id": "mock-task-1", "status": "failed", "success": False,
                 "error": {"code": "VideoDecodeFailed", "message": "视频无法解码"}}))
        with patch.object(U.subprocess, "run", side_effect=outputs) as process:
            self.run_job()
            with self.assertRaisesRegex(ValueError, "视频无法解码"):
                self.run_job(False)
            with self.assertRaisesRegex(ValueError, "失败或取消"):
                self.run_job(False)
            self.assertEqual(process.call_count, 2)
        self.assertEqual(json.loads((self.work / "receipt.json").read_text())["status"], "failed")
        self.assertIn("VideoDecodeFailed", (self.work / "result.json").read_text(encoding="utf-8"))

    def test_rejected_submission_is_not_reported_as_unknown(self):
        outputs = self.cli_outputs((1, {"success": False, "error": "跨服务授权未完成"}))
        with patch.object(U.subprocess, "run", side_effect=outputs) as process:
            with self.assertRaisesRegex(ValueError, "拒绝提交：跨服务授权未完成"):
                self.run_job()
            with self.assertRaisesRegex(ValueError, "被服务拒绝"):
                self.run_job()
            self.assertEqual(process.call_count, 1)
        self.assertEqual(json.loads((self.work / "receipt.json").read_text())["status"], "submit_failed")

    def test_query_error_without_terminal_status_keeps_task_pending(self):
        outputs = self.cli_outputs((0, {"task_id": "mock-task-1"}),
                                   (1, {"task_id": "mock-task-1", "success": False, "error": "HTTP 503"}),
                                   (0, {"task_id": "mock-task-1", "status": "running"}))
        with patch.object(U.subprocess, "run", side_effect=outputs):
            self.run_job()
            with self.assertRaisesRegex(ValueError, "HTTP 503"):
                self.run_job(False)
            self.assertEqual(json.loads((self.work / "receipt.json").read_text())["status"], "queued")
            self.assertEqual(self.run_job(False), "running")

    def test_changed_source_or_goal_cannot_reuse_old_analysis(self):
        with patch.object(U, "call_cli", return_value={"task_id": "mock-task-1"}) as call:
            self.run_job()
            self.video.write_bytes(b"different video")
            self.request = U.request_for([str(self.video)], "理解真实动作与可用区间", "Quality")
            with self.assertRaisesRegex(ValueError, "输入已改变"):
                self.run_job()
            self.assertEqual(call.call_count, 1)

    def test_no_project_key_cannot_fall_back_to_environment(self):
        self.env.write_text("MEDIAKIT_API_KEY=\n")
        with patch.dict(U.os.environ, {"MEDIAKIT_API_KEY": "MOCK_AMBIENT_KEY"}), \
                patch.object(U, "call_cli") as call:
            with self.assertRaisesRegex(ValueError, "MEDIAKIT_API_KEY ABSENT"):
                self.run_job()
            call.assert_not_called()
            self.assertFalse(self.work.exists())

    def test_completed_without_analysis_is_not_usable(self):
        with patch.object(U, "call_cli", side_effect=[{"task_id": "mock-task-1"},
                {"task_id": "mock-task-1", "status": "completed", "contents": []}]):
            self.run_job()
            with self.assertRaisesRegex(ValueError, "缺少分析正文"):
                self.run_job(False)
        self.assertFalse((self.work / "analysis.md").exists())

    def test_dry_run_has_no_key_cli_or_output_directory(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("请分析实际画面")
        with patch.object(sys, "argv", ["understand_video.py", "--videos", str(self.video),
                "--prompt", str(prompt), "--work", str(self.work), "--dry-run"]), \
                patch.object(U, "load_env") as env, patch.object(U, "call_cli") as call, \
                redirect_stdout(StringIO()) as output:
            self.assertEqual(U.main(), 0)
            self.assertEqual(json.loads(output.getvalue())["scene"], "editing")
            env.assert_not_called()
            call.assert_not_called()
        self.assertFalse(self.work.exists())

    def test_cli_key_is_env_only_and_error_logs_are_not_exposed(self):
        response = subprocess.CompletedProcess([], 0, '{"task_id":"mock-task-1"}', "")
        with patch.object(U.subprocess, "run", return_value=response) as process:
            U.call_cli("mediakit-cli", ["shared", "query-task", "--task-id", "mock-task-1"], "MOCK_NOT_A_REAL_KEY")
            self.assertNotIn("MOCK_NOT_A_REAL_KEY", " ".join(process.call_args.args[0]))
            self.assertEqual(process.call_args.kwargs["env"]["MEDIAKIT_API_KEY"], "MOCK_NOT_A_REAL_KEY")
        response = subprocess.CompletedProcess([], 1, "MOCK_NOT_A_REAL_KEY", "MOCK_NOT_A_REAL_KEY")
        with patch.object(U.subprocess, "run", return_value=response):
            with self.assertRaises(ValueError) as error:
                U.call_cli("mediakit-cli", [], "MOCK_NOT_A_REAL_KEY")
            self.assertNotIn("MOCK_NOT_A_REAL_KEY", str(error.exception))


if __name__ == "__main__":
    unittest.main()
