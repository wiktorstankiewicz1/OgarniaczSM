"""Public-contract tests for Archviz Studio; no live provider or production files."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import socket
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

import numpy as np
from PIL import Image, ImageCms

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from archviz_core import StudioProject, rasterize_annotations


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixels(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB")).copy()


def rectangle(ident, bounds, role="edit"):
    return {"id": ident, "number": 1, "type": "rectangle", "bounds": bounds,
            "points": [], "width": 6, "role": role, "comment": ident,
            "color": "#ff553f"}


def pen(ident="edge", role="edit"):
    return {"id": ident, "number": 1, "type": "pen",
            "bounds": [20, 20, 104, 76], "points": [[20, 20], [62, 48], [104, 76]],
            "width": 6, "role": role, "comment": "Repair only this joining edge",
            "color": "#ff553f"}


class ArchvizCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="archviz-qa-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        self.output = self.root / "approved"
        self.work = self.root / "work"
        y, x = np.mgrid[:96, :128]
        # Fine floor texture, a hard furniture edge, and one antialiased strip.
        image = np.stack([80 + x % 65, 65 + y % 60, 45 + (x + y) % 60], -1).astype("uint8")
        image[25:74, 40:48] = [43, 34, 26]
        image[25:74, 48] = [78, 65, 51]
        self.source = self.inputs / "Elektrovnia_test.png"
        Image.fromarray(image).save(self.source,
            icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        self.original_hash = sha(self.source)
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Live network forbidden in unit tests"))
        self.mock_network = self.network.start()
        self.addCleanup(self.network.stop)
        self.project = StudioProject.create("QA contract", str(self.work),
                                            [str(self.inputs)], str(self.output))

    def import_one(self):
        state = self.project.import_images([str(self.source)])
        self.assertEqual(1, len(state["frames"]))
        frame = state["frames"][0]
        return frame, frame["active_revision_id"]

    def completed_color(self, frame, revision, annotations=None, **options):
        job = self.project.create_job(frame["id"], revision, "color", annotations or
            [rectangle("light", [12, 12, 106, 82])], options={"brightness": 1.15, **options})
        result = self.project.run_job(job["id"])
        self.assertEqual("completed", result["status"], result)
        candidate = self.project.get_revision(frame["id"], result["result_revision_id"])
        return result, candidate

    def test_import_freezes_native_baseline_without_approving_or_changing_source(self):
        frame, revision = self.import_one()
        image = self.project.image_path(frame["id"], revision)
        self.assertTrue(Path(image).is_file())
        np.testing.assert_array_equal(pixels(self.source), pixels(image))
        self.assertEqual(self.original_hash, sha(self.source))
        self.assertIsNone(frame["approved_revision_id"])
        self.assertFalse(list(self.output.glob("*.jpg")))
        self.mock_network.assert_not_called()

    def test_color_changes_only_selection_and_protects_full_aa_strip(self):
        frame, revision = self.import_one()
        baseline_path = self.project.image_path(frame["id"], revision)
        baseline_hash = sha(baseline_path)
        before = pixels(baseline_path)
        _, candidate = self.completed_color(frame, revision, [
            rectangle("edit", [12, 12, 106, 82]),
            rectangle("person-and-AA", [38, 22, 51, 77], "protect")])
        after = pixels(self.project.image_path(frame["id"], candidate["id"]))
        changed = np.any(before != after, axis=2)
        allowed = np.zeros(before.shape[:2], bool)
        allowed[12:83, 12:107] = True
        self.assertGreater(int(changed.sum()), 0)
        self.assertFalse(np.any(changed & ~allowed))
        self.assertFalse(np.any(changed[22:78, 38:52]))
        self.assertEqual(baseline_hash, sha(baseline_path))
        self.assertEqual(self.original_hash, sha(self.source))
        self.assertEqual("candidate", candidate["status"])
        self.mock_network.assert_not_called()

    def test_saving_notes_rejects_wrong_image_hash_and_preserves_previous_notes(self):
        frame, revision = self.import_one()
        info = self.project.get_revision(frame["id"], revision)
        accepted = [rectangle("right-version", [10, 10, 30, 30])]
        self.project.save_annotations(frame["id"], revision, accepted, info["sha256"])
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.save_annotations(frame["id"], revision,
                [rectangle("wrong-version", [30, 30, 50, 50])], "0" * 64)
        saved = self.project.get_revision(frame["id"], revision)
        self.assertEqual(["right-version"], [item["id"] for item in saved["annotations"]])

    def test_tint_removes_magenta_and_warmth_preserves_mask_and_protection(self):
        frame, revision = self.import_one()
        before = pixels(self.project.image_path(frame["id"], revision))
        marks = [rectangle("material", [12, 12, 106, 82]),
                 rectangle("accepted-AA", [38, 22, 51, 77], "protect")]
        region = np.zeros(before.shape[:2], bool)
        region[12:83, 12:107] = True
        interior = np.zeros(before.shape[:2], bool)
        interior[30:65, 60:90] = True
        for options, direction in [({"tint": -.15}, (-1, 1, -1)),
                                   ({"tint": .15}, (1, -1, 1)),
                                   ({"warmth": .15}, (1, 0, -1))]:
            with self.subTest(options=options):
                _, candidate = self.completed_color(frame, revision, marks,
                                                     brightness=1, **options)
                after = pixels(self.project.image_path(frame["id"], candidate["id"]))
                changed = np.any(before != after, axis=2)
                self.assertFalse(np.any(changed & ~region))
                np.testing.assert_array_equal(before[22:78, 38:52], after[22:78, 38:52])
                channel_delta = after[interior].astype(float).mean(0) - before[interior].mean(0)
                for channel, sign in enumerate(direction):
                    if sign:
                        self.assertGreater(channel_delta[channel] * sign, 1)
                    else:
                        self.assertLess(abs(channel_delta[channel]), .1)
        self.assertEqual(self.original_hash, sha(self.source))
        self.mock_network.assert_not_called()

    def test_each_candidate_keeps_its_actual_parent_and_old_image_is_immutable(self):
        frame, source_revision = self.import_one()
        old_path = self.project.image_path(frame["id"], source_revision)
        old_sha = sha(old_path)
        _, first = self.completed_color(frame, source_revision)
        _, sibling = self.completed_color(frame, source_revision, brightness=0.85)
        self.assertNotEqual(first["id"], sibling["id"])
        self.assertEqual(source_revision, first["parent_id"])
        self.assertEqual(source_revision, sibling["parent_id"])
        self.assertEqual(old_sha, sha(old_path))
        reopened = StudioProject(str(self.work))
        self.assertEqual(first["sha256"], reopened.get_revision(frame["id"], first["id"])["sha256"])
        self.assertEqual(3, len(reopened.snapshot()["frames"][0]["revisions"]))

    def test_completed_job_reopen_and_rerun_never_make_duplicate_revision(self):
        frame, revision = self.import_one()
        job, candidate = self.completed_color(frame, revision)
        reopened = StudioProject(str(self.work))
        again = reopened.run_job(job["id"])
        self.assertEqual("completed", again["status"])
        self.assertEqual(candidate["id"], again["result_revision_id"])
        self.assertEqual(2, len(reopened.snapshot()["frames"][0]["revisions"]))
        self.mock_network.assert_not_called()

    def test_technical_pass_does_not_approve_or_export_until_explicit_human_action(self):
        frame, revision = self.import_one()
        _, candidate = self.completed_color(frame, revision)
        self.assertEqual("candidate", candidate["status"])
        self.assertIsNone(self.project.snapshot()["frames"][0]["approved_revision_id"])
        try:
            self.project.export_approved()
        except (ValueError, RuntimeError):
            pass
        self.assertFalse(list(self.output.glob("*.jpg")))
        state = self.project.approve(frame["id"], candidate["id"])
        self.assertEqual(candidate["id"], state["frames"][0]["approved_revision_id"])
        self.project.export_approved()
        target = self.output / "Elektrovnia_test.jpg"
        self.assertTrue(target.is_file())
        with Image.open(target) as image:
            image.load()
            self.assertEqual((128, 96), image.size)
        self.assertEqual(["Elektrovnia_test.jpg"], sorted(p.name for p in self.output.iterdir()))
        self.assertEqual(self.original_hash, sha(self.source))

    def test_new_unapproved_revision_does_not_replace_last_approved_export(self):
        frame, revision = self.import_one()
        _, approved = self.completed_color(frame, revision)
        self.project.approve(frame["id"], approved["id"])
        self.project.export_approved()
        target = self.output / "Elektrovnia_test.jpg"
        prior = sha(target)
        _, new = self.completed_color(frame, approved["id"], brightness=0.8)
        self.project.export_approved()
        self.assertEqual(prior, sha(target))
        self.project.approve(frame["id"], new["id"])
        self.project.export_approved()
        self.assertNotEqual(prior, sha(target))
        self.assertEqual(["Elektrovnia_test.jpg"], sorted(p.name for p in self.output.iterdir()))

    def test_duplicate_export_names_cannot_partially_publish(self):
        other = self.root / "other"
        other.mkdir()
        duplicate = other / self.source.name
        duplicate.write_bytes(self.source.read_bytes())
        try:
            state = self.project.import_images([str(self.source), str(duplicate)])
        except (ValueError, RuntimeError):
            self.assertFalse(list(self.output.glob("*.jpg")))
            return
        self.assertEqual(2, len(state["frames"]))
        for frame in state["frames"]:
            _, candidate = self.completed_color(frame, frame["active_revision_id"])
            self.project.approve(frame["id"], candidate["id"])
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.export_approved()
        self.assertFalse(list(self.output.glob("*.jpg")))

    def test_output_cannot_overwrite_original_input_directory(self):
        # Validation may happen on project creation, configuration, or export;
        # it must happen before any original can be replaced.
        try:
            project = StudioProject.create("Unsafe", str(self.root / "unsafe-work"),
                                           [str(self.inputs)], str(self.inputs))
        except (ValueError, RuntimeError):
            self.assertEqual(self.original_hash, sha(self.source))
            return
        state = project.import_images([str(self.source)])
        frame = state["frames"][0]
        project.approve(frame["id"], frame["active_revision_id"])
        with self.assertRaises((ValueError, RuntimeError)):
            project.export_approved()
        self.assertEqual(self.original_hash, sha(self.source))
        self.assertEqual([self.source.name], sorted(p.name for p in self.inputs.iterdir()))

    def test_pen_repair_kit_is_a_narrow_band_not_its_bounding_rectangle(self):
        frame, revision = self.import_one()
        kit = self.project.export_repair_kit(frame["id"], revision, [pen()])
        for key in ["kit_path", "target_path", "mask_path", "manifest_path", "suggested_result_path"]:
            self.assertIn(key, kit)
        with Image.open(kit["mask_path"]) as image:
            band = np.asarray(image.convert("L"))
        self.assertGreater(np.count_nonzero(band), 0)
        self.assertLess(np.count_nonzero(band), 84 * 56 // 3)
        self.mock_network.assert_not_called()

    def test_external_repair_import_masks_copyback_and_retains_native_parent(self):
        frame, revision = self.import_one()
        baseline = pixels(self.project.image_path(frame["id"], revision))
        original_frozen_sha = sha(self.project.image_path(frame["id"], revision))
        annotations = [pen(), rectangle("protected-crossing", [57, 40, 67, 55], "protect")]
        kit = self.project.export_repair_kit(frame["id"], revision, annotations)
        with Image.open(kit["target_path"]) as target:
            edited = Image.new("RGB", target.size, (196, 49, 34))
        result_path = Path(kit["suggested_result_path"])
        edited.save(result_path)
        result = self.project.import_repair(frame["id"], revision, kit["kit_path"], str(result_path))
        after = pixels(self.project.image_path(frame["id"], result["id"]))
        self.assertEqual(baseline.shape, after.shape)
        changed = np.any(baseline != after, axis=2)
        self.assertGreater(changed.sum(), 0)
        self.assertFalse(changed[0:12].any())
        self.assertFalse(changed[85:].any())
        self.assertFalse(changed[40:56, 57:68].any())
        self.assertEqual("candidate", result["status"])
        self.assertEqual(revision, result["parent_id"])
        self.assertEqual(original_frozen_sha, sha(self.project.image_path(frame["id"], revision)))
        self.assertIsNone(self.project.snapshot()["frames"][0]["approved_revision_id"])

    def test_external_repair_wrong_dimensions_rejected_without_revision(self):
        frame, revision = self.import_one()
        kit = self.project.export_repair_kit(frame["id"], revision, [pen()])
        with Image.open(kit["target_path"]) as target:
            wrong = Image.new("RGB", (target.width - 1, target.height))
        result = Path(kit["suggested_result_path"])
        wrong.save(result)
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.import_repair(frame["id"], revision, kit["kit_path"], str(result))
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))

    def test_external_repair_kit_cannot_be_applied_to_another_revision(self):
        frame, revision = self.import_one()
        kit = self.project.export_repair_kit(frame["id"], revision, [pen()])
        _, later = self.completed_color(frame, revision)
        result = Path(kit["suggested_result_path"])
        with Image.open(kit["target_path"]) as target:
            Image.new("RGB", target.size, (194, 38, 37)).save(result)
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.import_repair(frame["id"], later["id"], kit["kit_path"], str(result))
        self.assertEqual(2, len(self.project.snapshot()["frames"][0]["revisions"]))

    def test_changed_frozen_parent_blocks_repair_import(self):
        frame, revision = self.import_one()
        kit = self.project.export_repair_kit(frame["id"], revision, [pen()])
        frozen = Path(self.project.image_path(frame["id"], revision))
        with Image.open(frozen) as image:
            changed = image.convert("RGB")
        changed.putpixel((1, 1), (255, 0, 0))
        changed.save(frozen)
        result = Path(kit["suggested_result_path"])
        with Image.open(kit["target_path"]) as target:
            Image.new("RGB", target.size, (194, 38, 37)).save(result)
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.import_repair(frame["id"], revision, kit["kit_path"], str(result))
        self.assertEqual(self.original_hash, sha(self.source))

    def test_diagnostics_are_reproducible_and_exclude_environment_credentials(self):
        frame, revision = self.import_one()
        self.completed_color(frame, revision)
        secret = "qa-only-secret-credential-321281238321"
        with patch.dict(os.environ, {"GEMINI_API_KEY": secret}):
            report = self.project.diagnostics()
        self.assertIn("path", report)
        path = Path(report["path"])
        self.assertTrue(path.exists())
        if path.is_dir():
            contents = b"\n".join(p.read_bytes() for p in path.rglob("*") if p.is_file())
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                contents = b"\n".join(archive.read(name) for name in archive.namelist())
        else:
            contents = path.read_bytes()
        self.assertNotIn(secret.encode(), contents)
        self.assertTrue(contents)
        self.mock_network.assert_not_called()

    def test_edge_rectangle_is_an_outline_with_inward_aa_and_hard_protection(self):
        selected = rectangle("outline", [20, 20, 104, 76])
        shield = rectangle("foreground-AA", [97, 38, 110, 57], "protect")
        outline, protection = rasterize_annotations((128, 96), [selected, shield], "edge", 6)
        filled, _ = rasterize_annotations((128, 96), [selected], "local", 6)
        self.assertEqual(0, outline[48, 60])
        self.assertGreater(filled[48, 60], 0)
        self.assertFalse(outline[38:58, 97:111].any())
        self.assertTrue(protection[38:58, 97:111].all())
        self.assertTrue(np.any((outline > 0) & (outline < 255)))
        self.assertLess(np.count_nonzero(outline), np.count_nonzero(filled) // 2)

    def test_nonfinite_mask_geometry_is_rejected_without_saving_annotations(self):
        frame, revision = self.import_one()
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.save_annotations(frame["id"], revision,
                [rectangle("nan", [20, float("nan"), 70, 60])])
        self.assertFalse(self.project.get_revision(frame["id"], revision)["annotations"])

    def test_budget_exhaustion_does_not_send_a_generation_request(self):
        frame, revision = self.import_one()
        self.project.update_settings(max_paid_calls=0)
        job = self.project.create_job(frame["id"], revision, "edge", [pen()])
        requests = []
        def provider(request, **kwargs):
            requests.append(request)
            if request.get_method() != "GET":
                raise AssertionError("Budget exhausted but generation was sent")
            return io.BytesIO(b'{"name":"models/gemini-3-pro-image","displayName":"Nano Banana Pro"}')
        with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-qa-key"}), \
                patch("urllib.request.urlopen", side_effect=provider):
            result = self.project.run_job(job["id"])
        self.assertEqual("failed", result["status"])
        self.assertEqual(0, self.project.snapshot().get("api_calls_used", 0))
        self.assertFalse(any(r.get_method() == "POST" for r in requests))
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))

    def test_unknown_paid_outcome_cannot_silently_retry_after_restart(self):
        frame, revision = self.import_one()
        job = self.project.create_job(frame["id"], revision, "edge", [pen()])
        requests = []
        def interrupted_provider(request, **kwargs):
            requests.append(request)
            if request.get_method() == "GET":
                return io.BytesIO(b'{"name":"models/gemini-3-pro-image","displayName":"Nano Banana Pro"}')
            raise urllib.error.URLError("Response lost after request dispatch")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-qa-key"}), \
                patch("urllib.request.urlopen", side_effect=interrupted_provider):
            result = self.project.run_job(job["id"])
            self.assertEqual("unknown", result["status"])
            reopened = StudioProject(str(self.work))
            with self.assertRaises((ValueError, RuntimeError)):
                reopened.run_job(job["id"])
        self.assertEqual(1, sum(r.get_method() == "POST" for r in requests))
        self.assertEqual("unknown", reopened.get_job(job["id"])["status"])
        self.assertEqual(1, self.project.snapshot().get("api_calls_used", 0))

    def test_changed_preflight_mask_blocks_execution_and_keeps_parent_intact(self):
        frame, revision = self.import_one()
        job = self.project.create_job(frame["id"], revision, "color", [pen()],
                                       options={"brightness": 1.2})
        path = self.work / job["artifacts"]["allowed_mask"]
        with Image.open(path) as source:
            altered = source.convert("L")
        altered.putpixel((2, 2), 255)
        altered.save(path)
        result = self.project.run_job(job["id"])
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.assertEqual(self.original_hash, sha(self.source))
        self.mock_network.assert_not_called()

    def test_explicit_restart_recovery_distinguishes_unpaid_paid_cached_and_live_jobs(self):
        frame, revision = self.import_one()
        cases = [
            ("orphan-unpaid", False, None, 4000000000, socket.gethostname(), "queued"),
            ("orphan-paid-no-reply", True, None, 4000000000, socket.gethostname(), "unknown"),
            ("orphan-paid-cached", True, True, 4000000000, socket.gethostname(), "queued"),
            ("orphan-paid-corrupt-cache", True, False, 4000000000, socket.gethostname(), "unknown"),
            ("live-local-worker", False, None, os.getpid(), socket.gethostname(), "running"),
            ("foreign-worker", False, None, 4000000000, "QA-other-machine", "running"),
        ]
        expected = {}
        for label, paid, cache_valid, pid, host, status in cases:
            job = self.project.create_job(frame["id"], revision, "edge", [pen(label)])
            state = self.project.snapshot()
            item = next(j for j in state["jobs"] if j["id"] == job["id"])
            item.update(status="running", worker_pid=pid, worker_host=host)
            if paid:
                item["paid_call_reserved_at"] = "2026-01-01T00:00:00+00:00"
            if cache_valid is not None:
                folder = self.work / "jobs" / job["id"]
                output = folder / "provider_output.png"
                Image.new("RGB", (128, 96), (91, 84, 70)).save(output)
                (folder / "provider_receipt.json").write_text(json.dumps({
                    "qa_fixture": True,
                    "output_sha256": sha(output) if cache_valid else "0" * 64,
                }), encoding="utf-8")
            # This fixture represents a process that died between persisted phases.
            (self.work / "project.json").write_text(json.dumps(state), encoding="utf-8")
            expected[job["id"]] = (label, status)
        recovered = self.project.recover_jobs()
        for job_id, (label, status) in expected.items():
            with self.subTest(case=label):
                self.assertEqual(status, self.project.get_job(job_id)["status"])
                if status == "running":
                    self.assertIn(job_id, recovered["skipped_live"])
                else:
                    self.assertIn(job_id, recovered["recovered"])
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.mock_network.assert_not_called()

    def test_explicit_recovery_can_release_own_dead_writer_but_preserves_unreadable_lock(self):
        self.import_one()
        lock = self.work / ".writer.lock"
        lock.write_text(json.dumps({"pid": 4000000000, "host": socket.gethostname()}), encoding="utf-8")
        self.project.recover_jobs()
        self.assertFalse(lock.exists())
        invalid = b"not-a-valid-writer-record"
        lock.write_bytes(invalid)
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.recover_jobs()
        self.assertEqual(invalid, lock.read_bytes())
        self.mock_network.assert_not_called()

    def test_cancel_queued_draft_never_spends_and_cannot_interrupt_running_or_unknown(self):
        frame, revision = self.import_one()
        draft = self.project.create_job(frame["id"], revision, "people", [pen()])
        result = self.project.cancel_job(draft["id"])
        self.assertEqual("cancelled", result["status"])
        with self.assertRaises((ValueError, RuntimeError)):
            self.project.run_job(draft["id"])
        recovered = StudioProject(str(self.work)).recover_jobs()
        self.assertNotIn(draft["id"], recovered["recovered"])
        self.assertEqual("cancelled", self.project.get_job(draft["id"])["status"])
        for status in ["running", "unknown"]:
            with self.subTest(status=status):
                job = self.project.create_job(frame["id"], revision, "people", [pen(status)])
                state = self.project.snapshot()
                item = next(j for j in state["jobs"] if j["id"] == job["id"])
                item.update(status=status, worker_pid=os.getpid(), worker_host=socket.gethostname())
                (self.work / "project.json").write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises((ValueError, RuntimeError)):
                    self.project.cancel_job(job["id"])
                self.assertEqual(status, self.project.get_job(job["id"])["status"])
        self.assertEqual(0, self.project.snapshot()["api_calls_used"])
        self.assertEqual(1, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.mock_network.assert_not_called()

    def test_failed_comfy_resume_can_change_only_composition_without_replacing_paid_inputs(self):
        frame, revision = self.import_one()
        original_options = {"brightness": 1.12, "compositor": "comfy",
                            "comfy_url": "http://127.0.0.1:18188",
                            "prompt": "Preserve this exact original instruction"}
        job = self.project.create_job(frame["id"], revision, "color", [pen()], original_options)
        original_job = self.project.get_job(job["id"])
        with patch.object(StudioProject, "_comfy", side_effect=RuntimeError("QA unavailable compositor")):
            failed = self.project.run_job(job["id"])
        self.assertEqual("failed", failed["status"])
        for forbidden in [{"prompt": "different"}, {"provider": "another"}]:
            with self.assertRaises((ValueError, RuntimeError)):
                self.project.set_resume_composition(job["id"], forbidden)
        self.project.set_resume_composition(job["id"], {"compositor": "local"})
        completed = self.project.run_job(job["id"])
        self.assertEqual("completed", completed["status"])
        resumed = self.project.get_job(job["id"])
        self.assertEqual(original_job["options"], resumed["options"])
        self.assertEqual(original_job["annotations"], resumed["annotations"])
        self.assertEqual(original_job["mask_preflight"], resumed["mask_preflight"])
        self.assertEqual("local", resumed["resume_composition_options"]["compositor"])
        self.assertEqual("local", self.project.get_revision(frame["id"], completed["result_revision_id"])["qa"]["compositor"])
        self.assertEqual(2, len(self.project.snapshot()["frames"][0]["revisions"]))
        self.assertEqual(0, self.project.snapshot()["api_calls_used"])
        for status in ["running", "unknown"]:
            with self.subTest(status=status):
                state = self.project.snapshot()
                item = next(j for j in state["jobs"] if j["id"] == job["id"])
                item["status"] = status
                (self.work / "project.json").write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises((ValueError, RuntimeError)):
                    self.project.set_resume_composition(job["id"], {"compositor": "local"})
        self.mock_network.assert_not_called()

    def test_cached_paid_output_survives_comfy_failure_and_resume_never_calls_provider(self):
        frame, revision = self.import_one()
        job = self.project.create_job(frame["id"], revision, "people", [pen()],
                                      {"compositor": "comfy", "prompt": "Saved paid input"})
        folder = self.work / "jobs" / job["id"]
        l, t, r, b = job["artifacts"]["crop_box"]
        cached = folder / "provider_output.png"
        Image.new("RGB", (r-l, b-t), (93, 86, 64)).save(cached)
        cached_sha = sha(cached)
        receipt = {"qa_fixture": True, "output_sha256": cached_sha,
                   "padded_size": [r-l, b-t], "crop_box": [l, t, r, b],
                   "model": "gemini-3-pro-image", "generationConfig": {
                       "thinkingConfig": {"thinkingLevel": "HIGH"}}}
        receipt_file = folder / "provider_receipt.json"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_sha = sha(receipt_file)
        state = self.project.snapshot()
        state["api_calls_used"] = 1
        next(j for j in state["jobs"] if j["id"] == job["id"])["paid_call_reserved_at"] = "2026-01-01T00:00:00+00:00"
        (self.work / "project.json").write_text(json.dumps(state), encoding="utf-8")
        with patch.object(StudioProject, "_comfy", side_effect=RuntimeError("QA compositor offline")):
            failed = self.project.run_job(job["id"])
        self.assertEqual("failed", failed["status"])
        reopened = StudioProject(str(self.work))
        reopened.set_resume_composition(job["id"], {"compositor": "local"})
        completed = reopened.run_job(job["id"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual(1, reopened.snapshot()["api_calls_used"])
        self.assertEqual(2, len(reopened.snapshot()["frames"][0]["revisions"]))
        self.assertEqual(cached_sha, sha(cached))
        self.assertEqual(receipt_sha, sha(receipt_file))
        self.assertEqual(receipt, reopened.get_job(job["id"])["receipt"])
        self.assertEqual(self.original_hash, sha(self.source))
        self.mock_network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
