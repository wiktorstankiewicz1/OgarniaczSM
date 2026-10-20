"""Updater isolation: never mutate an installed app from a source checkout."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import autoupdate


class UpdateIsolationTests(unittest.TestCase):
    def test_source_run_does_not_read_production_or_spawn_updater(self):
        with patch.object(sys, "frozen", False, create=True), \
             patch.object(autoupdate, "_get_remote_manifest") as manifest, \
             patch.object(autoupdate.subprocess, "Popen") as popen, \
             patch.object(os, "_exit") as exit_process:
            autoupdate.check_for_updates_once(silent=False)
        manifest.assert_not_called()
        popen.assert_not_called()
        exit_process.assert_not_called()

    def test_source_run_does_not_start_background_update_thread(self):
        with patch.object(sys, "frozen", False, create=True), \
             patch.object(autoupdate.threading, "Thread") as thread:
            autoupdate.start_periodic_update_check()
        thread.assert_not_called()

    def test_frozen_app_still_passes_new_release_to_updater(self):
        release = {"version": "0.5.2.29", "src_path": "C:/mock-release"}
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(autoupdate, "_get_remote_manifest", return_value=release), \
             patch.object(autoupdate, "_get_local_version", return_value="0.5.2.28"), \
             patch.object(autoupdate, "_log"), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(autoupdate.subprocess, "Popen") as popen, \
             patch.object(os, "_exit") as exit_process:
            autoupdate.check_for_updates_once(silent=False)
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("--version") + 1], "0.5.2.29")
        self.assertEqual(args[args.index("--dst") + 1], str(autoupdate.APP_DIR))
        exit_process.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
