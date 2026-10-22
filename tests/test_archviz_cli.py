"""CLI exit codes, safe resume, and frozen-app file picker IPC; no live API."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import archviz_cli
from archviz_core import StudioProject


class ArchvizCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="archviz-cli-qa-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        inputs = self.root / "input"
        inputs.mkdir()
        self.source = inputs / "test.png"
        Image.new("RGB", (64, 48), (110, 85, 70)).save(self.source)
        self.work = self.root / "work"
        self.project = StudioProject.create("CLI QA", str(self.work), [str(inputs)],
                                            str(self.root / "output"))
        frame = self.project.import_images([str(self.source)])["frames"][0]
        self.frame, self.revision = frame["id"], frame["active_revision_id"]
        self.marks = [{"id": "material", "number": 1, "type": "rectangle",
                       "role": "edit", "width": 6, "bounds": [10, 10, 45, 35],
                       "points": [], "comment": "test"}]
        self.project.save_annotations(self.frame, self.revision, self.marks)
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("No live network"))
        self.mock_network = self.network.start()
        self.addCleanup(self.network.stop)

    def test_cli_known_failure_returns_nonzero_and_preserves_parent(self):
        options = self.root / "invalid-options.json"
        options.write_text('{"brightness":0}', encoding="utf-8")
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = archviz_cli.main(["run", "--work", str(self.work), "--frame", self.frame,
                                    "--revision", self.revision, "--operation", "color",
                                    "--options", str(options)])
        self.assertEqual(1, code)
        self.assertEqual("failed", json.loads(stream.getvalue())["status"])
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.mock_network.assert_not_called()

    def test_cli_resume_completed_job_reuses_revision_without_provider_call(self):
        job = self.project.create_job(self.frame, self.revision, "color", self.marks,
                                      {"brightness":1.1})
        completed = self.project.run_job(job["id"])
        self.assertEqual("completed", completed["status"])
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = archviz_cli.main(["resume", "--work", str(self.work), "--job", job["id"]])
        self.assertEqual(0, code)
        self.assertEqual(completed["result_revision_id"], json.loads(stream.getvalue())["result_revision_id"])
        self.assertEqual(2, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.assertEqual(0, self.project.snapshot()["api_calls_used"])
        self.mock_network.assert_not_called()

    def test_picker_file_channel_works_when_frozen_stdout_is_none(self):
        result = self.root / "picker-result.json"
        expected = {"paths":[str(self.source)]}
        with patch.object(archviz_cli, "pick", return_value=expected) as pick, \
                patch.object(sys, "stdout", None):
            code = archviz_cli.main(["pick", "images", "--result-file", str(result)])
        self.assertEqual(0, code)
        self.assertEqual(expected, json.loads(result.read_text(encoding="utf-8")))
        pick.assert_called_once_with("images")
        self.mock_network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
