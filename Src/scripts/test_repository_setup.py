"""Repository structure checks and dual-remote failure-path tests."""
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch
import sync_remotes

ROOT = Path(__file__).resolve().parents[2]


def result(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class RepositorySetupTests(unittest.TestCase):
    def test_project_root_and_readme_links(self):
        for entry in ("README.md", "AGENTS.md", ".gitignore", "Docs", "Src"):
            self.assertTrue((ROOT / entry).exists(), entry)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", readme):
            if not target.startswith(("https://", "http://", "#")):
                self.assertTrue((ROOT / target.split("#")[0]).exists(), target)

    def test_private_files_ignored_but_template_retained(self):
        for name in (".env", ".env.production", "Src/backend/local.db", "Src/frontend/node_modules/package/index.js", ".vs/cache", "MeetFlow-course-starter.zip", "软件工程实践课程教案.pdf"):
            check = subprocess.run(["git", "check-ignore", "--no-index", "-q", name], cwd=ROOT)
            self.assertEqual(check.returncode, 0, name)
        check = subprocess.run(["git", "check-ignore", "--no-index", "-q", "Src/backend/.env.example"], cwd=ROOT)
        self.assertEqual(check.returncode, 1)

    def test_sync_verifies_both_tips(self):
        responses = [result(stdout="main\n"), result(stdout="abc\n"), result(), result(stdout="abc\trefs/heads/main\n"), result(), result(stdout="abc\trefs/heads/main\n")]
        with patch.object(sync_remotes, "git", side_effect=responses) as mocked:
            self.assertEqual(sync_remotes.sync(), 0)
            self.assertEqual([call.args[1] for call in mocked.call_args_list if call.args[0] == "push"], ["gitee", "github"])

    def test_sync_attempts_second_remote_after_first_fails(self):
        responses = [result(stdout="main\n"), result(stdout="abc\n"), result(1, stderr="denied"), result(), result(stdout="abc\trefs/heads/main\n")]
        with patch.object(sync_remotes, "git", side_effect=responses) as mocked:
            self.assertEqual(sync_remotes.sync(), 1)
            self.assertEqual([call.args[1] for call in mocked.call_args_list if call.args[0] == "push"], ["gitee", "github"])

    def test_sync_rejects_mismatched_remote_tip(self):
        responses = [result(stdout="main\n"), result(stdout="abc\n"), result(), result(stdout="different\trefs/heads/main\n"), result(), result(stdout="abc\trefs/heads/main\n")]
        with patch.object(sync_remotes, "git", side_effect=responses):
            self.assertEqual(sync_remotes.sync(), 1)


if __name__ == "__main__":
    unittest.main()
