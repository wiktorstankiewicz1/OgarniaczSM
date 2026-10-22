"""Independent release/updater boundaries. Only temporary directories and fake EXEs."""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import zipfile
from concurrent.futures import Future

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import updater
import autoupdate


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ogarniacz-release-qa-")
        self.addCleanup(self.temp.cleanup)
        # GitHub's Windows TEMP can use RUNNER~1 while production resolves the
        # same directory to runneradmin. Fault-injection predicates must agree.
        self.root = Path(self.temp.name).resolve()
        self.src = self.root / "release"
        self.dst = self.root / "installation"
        self.src.mkdir()
        self.dst.mkdir()
        self.version = "0.5.2.29"
        self.commit = "a" * 40
        for name, content in {
            "OgarniaczSM.exe": b"QA-fake-new-app-not-executable",
            "OgarniaczUpdater.exe": b"QA-fake-new-updater-not-executable",
            "archviz_studio.html": b"<html>QA release fixture</html>",
            "config.example.json": b'{"tiles":[]}',
            "version.json": json.dumps({"version": self.version, "commit": self.commit}).encode(),
        }.items():
            (self.src / name).write_bytes(content)
        self.refresh_manifest()
        for name, content in {
            "OgarniaczSM.exe": b"QA-old-app",
            "OgarniaczUpdater.exe": b"QA-old-updater",
            "obsolete.dll": b"QA-old-distributed-file",
            "version.json": b'{"version":"0.5.2.28"}',
            "config.json": b'{"custom":"keep this configuration"}',
            "autoupdate.log": b"keep previous update evidence\n",
            "ArchvizStudio/registry.json": b'{"active_work_dir":"QA-project"}',
            "ArchvizStudio/local-note.txt": b"keep complete local project metadata",
        }.items():
            path = self.dst / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.original_install = file_snapshot(self.dst)
        self.launch = patch.object(updater.subprocess, "Popen",
                                   side_effect=AssertionError("No application launches in release unit tests"))
        self.mock_launch = self.launch.start()
        self.addCleanup(self.launch.stop)

    def refresh_manifest(self):
        files = [{"path": p.relative_to(self.src).as_posix(), "sha256": digest(p),
                  "size": p.stat().st_size}
                 for p in sorted(self.src.rglob("*"))
                 if p.is_file() and p.name != "file_manifest.json"]
        self.manifest = {"schema_version": 1, "version": self.version,
                         "commit": self.commit, "files": files}
        (self.src / "file_manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.manifest_sha = digest(self.src / "file_manifest.json")

    def test_verified_install_preserves_user_configuration_registry_and_complete_backup(self):
        info = updater.verify_release(self.src, self.manifest_sha)
        self.assertEqual(self.version, info["version"])
        self.assertEqual(self.commit, info["commit"])
        receipt = updater.copy_dir(self.src, self.dst, self.manifest_sha, self.version)
        self.assertEqual(self.version, receipt["version"])
        for name in ["config.json", "autoupdate.log", "ArchvizStudio/registry.json",
                     "ArchvizStudio/local-note.txt"]:
            self.assertEqual(self.original_install[name], (self.dst / name).read_bytes())
        for record in self.manifest["files"]:
            self.assertEqual(record["sha256"], digest(self.dst / record["path"]))
        self.assertFalse((self.dst / "obsolete.dll").exists())
        self.assertEqual(self.original_install, file_snapshot(Path(receipt["backup"])))
        updater.verify_release(self.dst, self.manifest_sha, allow_userdata=True)
        self.mock_launch.assert_not_called()

    def test_wrong_manifest_hash_or_corrupt_asset_blocks_before_install_mutation(self):
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.copy_dir(self.src, self.dst, "0" * 64, self.version)
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        (self.src / "archviz_studio.html").write_bytes(b"corrupt package")
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.copy_dir(self.src, self.dst, self.manifest_sha, self.version)
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        self.mock_launch.assert_not_called()

    def test_requested_version_mismatch_and_extra_unmanifested_payload_are_rejected(self):
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.copy_dir(self.src, self.dst, self.manifest_sha, "99.0.0.1")
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        (self.src / "unreviewed.dll").write_bytes(b"not part of the release manifest")
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.verify_release(self.src, self.manifest_sha)
        self.mock_launch.assert_not_called()

    def test_package_with_invalid_app_version_metadata_is_rejected_even_with_valid_hashes(self):
        (self.src / "version.json").write_text('{"version":"99.0.0.1"}', encoding="utf-8")
        self.refresh_manifest()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.verify_release(self.src, self.manifest_sha)
        self.assertEqual(self.original_install, file_snapshot(self.dst))

    def test_manifest_paths_cannot_escape_the_release_or_use_a_windows_drive(self):
        for unsafe in ["../escaped.bin", "nested/../../escaped.bin", "C:/escaped.bin",
                       "/escaped.bin", "..\\escaped.bin"]:
            with self.subTest(path=unsafe):
                broken = {**self.manifest, "files": [*self.manifest["files"],
                    {"path": unsafe, "sha256": "0" * 64, "size": 0}]}
                (self.src / "file_manifest.json").write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    updater.verify_release(self.src, digest(self.src / "file_manifest.json"))
        self.assertFalse((self.root / "escaped.bin").exists())
        self.assertEqual(self.original_install, file_snapshot(self.dst))

    def test_source_destination_overlap_is_rejected_without_any_changes(self):
        package_before = file_snapshot(self.src)
        for destination in [self.src, self.src / "inside", self.root]:
            with self.subTest(destination=str(destination)):
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    updater.copy_dir(self.src, destination, self.manifest_sha, self.version)
                self.assertEqual(package_before, file_snapshot(self.src))
                self.assertEqual(self.original_install, file_snapshot(self.dst))

    def test_copy_permission_failure_keeps_old_version_and_does_not_launch(self):
        original_copytree = updater.shutil.copytree
        def locked_source(src, dst, *args, **kwargs):
            if Path(src) == self.src:
                raise PermissionError("QA simulated unreadable release payload during staging")
            return original_copytree(src, dst, *args, **kwargs)
        argv = ["OgarniaczUpdater.exe", "--src", str(self.src), "--dst", str(self.dst),
                "--launch", str(self.dst / "OgarniaczSM.exe"), "--version", self.version,
                "--manifest-sha256", self.manifest_sha]
        with patch.object(sys, "argv", argv), patch.object(updater.shutil, "copytree", side_effect=locked_source):
            try:
                code = updater.main()
            except (ValueError, RuntimeError, OSError, SystemExit) as error:
                if isinstance(error, SystemExit):
                    self.assertNotIn(error.code, [None, 0])
            else:
                self.assertNotIn(code, [None, 0])
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        self.mock_launch.assert_not_called()

    def test_failed_stage_activation_rolls_back_entire_old_installation(self):
        alias_hop = self.root / "alias-hop"
        alias_hop.mkdir()
        source_alias = alias_hop / ".." / self.src.name
        destination_alias = alias_hop / ".." / self.dst.name
        original_rename = Path.rename
        activation_attempted = []
        def fail_activation(path, target):
            if path.name.startswith(self.dst.name + ".staging-") and Path(target) == self.dst:
                activation_attempted.append(True)
                raise PermissionError("QA simulated Windows destination lock during activation")
            return original_rename(path, target)
        with patch.object(Path, "rename", fail_activation):
            with self.assertRaises(PermissionError):
                updater.copy_dir(source_alias, destination_alias, self.manifest_sha, self.version)
        self.assertEqual([True], activation_attempted)
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        self.assertFalse(list(self.root.glob("installation.staging-*")))
        self.mock_launch.assert_not_called()

    def test_locked_installed_directory_never_changes_version_or_launches(self):
        original_rename = Path.rename
        def locked_installation(path, target):
            if path == self.dst:
                raise PermissionError("QA simulated running EXE holding its installation directory")
            return original_rename(path, target)
        argv = ["--src", str(self.src), "--dst", str(self.dst), "--launch",
                str(self.dst / "OgarniaczSM.exe"), "--version", self.version,
                "--manifest-sha256", self.manifest_sha]
        with patch.object(Path, "rename", locked_installation):
            with self.assertRaises(PermissionError):
                updater.main(argv)
        self.assertEqual(self.original_install, file_snapshot(self.dst))
        self.assertFalse((self.dst / "installation_receipt.json").exists())
        self.mock_launch.assert_not_called()

    def test_autoupdate_refuses_unverified_inventory_or_remote_identity(self):
        release = {"version": self.version, "commit": self.commit,
                   "file_manifest_sha256": self.manifest_sha}
        for changed in [{"file_manifest_sha256": "0" * 64},
                        {"commit": "b" * 40}, {"version": "0.5.2.30"},
                        {"file_manifest_sha256": None}]:
            with self.subTest(changed=changed):
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    autoupdate._verified_updater(self.src, {**release, **changed})
        (self.src / "OgarniaczUpdater.exe").write_bytes(b"unverified helper replacement")
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            autoupdate._verified_updater(self.src, release)
        self.mock_launch.assert_not_called()

    def test_verified_updater_is_a_byte_identical_temporary_copy_from_new_release(self):
        temporary_helper = self.root / "verified-helper"
        temporary_helper.mkdir()
        release = {"version": self.version, "commit": self.commit,
                   "file_manifest_sha256": self.manifest_sha}
        with patch.object(autoupdate.tempfile, "mkdtemp", return_value=str(temporary_helper)):
            copied = autoupdate._verified_updater(self.src, release)
        self.assertEqual(temporary_helper / "OgarniaczUpdater.exe", copied)
        self.assertEqual(digest(self.src / "OgarniaczUpdater.exe"), digest(copied))
        self.assertNotEqual(digest(self.dst / "OgarniaczUpdater.exe"), digest(copied))
        self.mock_launch.assert_not_called()

    def test_temporary_updater_copy_corruption_is_detected_before_launch(self):
        temporary_helper = self.root / "corrupt-helper"
        temporary_helper.mkdir()
        release = {"version": self.version, "commit": self.commit,
                   "file_manifest_sha256": self.manifest_sha}
        original_copy = autoupdate.shutil.copy2
        def corrupt_copy(src, dst, *args, **kwargs):
            result = original_copy(src, dst, *args, **kwargs)
            Path(dst).write_bytes(b"QA simulated partial SMB copy")
            return result
        with patch.object(autoupdate.tempfile, "mkdtemp", return_value=str(temporary_helper)), \
                patch.object(autoupdate.shutil, "copy2", side_effect=corrupt_copy):
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                autoupdate._verified_updater(self.src, release)
        self.mock_launch.assert_not_called()

    def test_frozen_autoupdate_resolves_installation_from_actual_executable(self):
        spec = importlib.util.spec_from_file_location("qa_frozen_autoupdate", autoupdate.__file__)
        module = importlib.util.module_from_spec(spec)
        alias_hop = self.root / "executable-alias-hop"
        alias_hop.mkdir()
        executable = alias_hop / ".." / "portable-install" / "OgarniaczSM.exe"
        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(executable)):
            spec.loader.exec_module(module)
        self.assertEqual(executable.parent.resolve(), module.APP_DIR)
        self.assertEqual(executable.resolve(), module.APP_EXE)
        self.mock_launch.assert_not_called()

    def test_registry_migrates_outside_installation_without_overwriting_existing_state(self):
        from archviz_server import default_registry
        local = self.root / "local-app-data"
        legacy = local / "OgarniaczSM" / "ArchvizStudio" / "registry.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"active_work_dir":"original-project"}', encoding="utf-8")
        original = legacy.read_bytes()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            target = default_registry()
            self.assertEqual(local / "StillMotion" / "ArchvizStudio" / "registry.json", target)
            self.assertEqual("original-project", json.loads(target.read_text())["active_work_dir"])
            target.write_text('{"active_work_dir":"new-active-project"}', encoding="utf-8")
            self.assertEqual(target, default_registry())
            self.assertEqual("new-active-project", json.loads(target.read_text())["active_work_dir"])
        self.assertEqual(original, legacy.read_bytes())

    def test_frozen_widget_only_reuses_the_exact_worker_build_identity(self):
        from archviz_runtime import compatible_service
        frozen = {"mode": "frozen", "version": self.version, "commit": self.commit}
        for actual, allowed in [(frozen, True),
                                ({**frozen, "commit": "b" * 40}, False),
                                ({**frozen, "version": "0.5.2.28"}, False),
                                ({**frozen, "mode": "source"}, False), (None, False)]:
            with self.subTest(worker=actual), \
                    patch("archviz_runtime.build_identity", return_value=frozen):
                self.assertEqual(allowed, compatible_service({"service": "archviz-studio", "build": actual}))
        with patch("archviz_runtime.build_identity", return_value={**frozen, "commit": None}):
            self.assertFalse(compatible_service({"service": "archviz-studio", "build": frozen}))
        with patch("archviz_runtime.build_identity", return_value={"mode": "source", "version": None, "commit": None}):
            self.assertTrue(compatible_service({"service": "archviz-studio", "build": frozen}))
            self.assertFalse(compatible_service({"service": "unrelated-worker", "build": frozen}))

    def test_real_http_shutdown_refuses_busy_jobs_and_requires_token_before_idle_handoff(self):
        from archviz_server import StudioHTTPServer, StudioService
        service = StudioService(self.root / "http-registry.json")
        server = StudioHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, route, token=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                headers = {"X-Studio-Token": token} if token else {}
                conn.request(method, route, body=b"{}" if method == "POST" else None, headers=headers)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        try:
            status, health = request("GET", "/api/health")
            self.assertEqual(200, status)
            self.assertEqual(os.getpid(), health["pid"])
            self.assertEqual(sys.executable, health["executable"])
            self.assertIn(health["build"]["mode"], ["source", "frozen"])
            self.assertEqual(403, request("POST", "/api/shutdown")[0])
            for state in ["queued", "running"]:
                with self.subTest(state=state):
                    service.projects = {"qa": types.SimpleNamespace(snapshot=lambda: {"jobs": [{"status": state}]})}
                    self.assertEqual(400, request("POST", "/api/shutdown", service.token)[0])
                    self.assertEqual(200, request("GET", "/api/health")[0])
            service.projects = {}
            service.futures = {"pending-qa": Future()}
            self.assertEqual(400, request("POST", "/api/shutdown", service.token)[0])
            service.futures = {}
            self.assertEqual(200, request("POST", "/api/shutdown", service.token)[0])
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        finally:
            server.shutdown()
            server.server_close()
            service.shutdown()

    def test_zip_traversal_symlink_and_nonempty_destination_are_rejected(self):
        for name, symlink in [("../escape.txt", False), ("C:/escape.txt", False),
                              ("..\\escape.txt", False), ("link", True)]:
            with self.subTest(name=name, symlink=symlink):
                archive = self.root / "unsafe.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    entry = zipfile.ZipInfo(name)
                    if symlink:
                        entry.create_system = 3
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(entry, b"../escape.txt" if symlink else b"unsafe")
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    updater.extract_zip_to(archive, self.root / "unpacked")
                self.assertFalse((self.root / "escape.txt").exists())
        good_zip = self.root / "safe.zip"
        with zipfile.ZipFile(good_zip, "w") as z:
            z.writestr("new.bin", b"new payload")
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            updater.extract_zip_to(good_zip, self.dst)
        self.assertEqual(self.original_install, file_snapshot(self.dst))


if __name__ == "__main__":
    unittest.main()
