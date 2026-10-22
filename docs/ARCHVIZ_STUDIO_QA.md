# Archviz Studio acceptance checks

This document records the independent acceptance plan. A plan is not a PASS.
Live run evidence belongs outside Git in:
`Y:/__PROJECTS/Elektrovnia/wizki/codex_test_poprawek/_archviz_studio_pilot/qa`.

## Protected production assets

`protected_sources_before.json` records SHA256, dimensions and lengths of all
five user-approved delivery JPGs, the five original renders, and both v7 lobby
lossless PNGs. Compare every recorded SHA again after module tests. None of
these files is a test output destination. The module's pilot project and final
export tests use separate work and output directories.

## Contract tests

From the isolated worktree, using the existing repository interpreter:

```powershell
& C:/Users/wikto/source/repos/OgarniaczSM/.venv/Scripts/python.exe -m unittest discover -s tests -v
& C:/Users/wikto/source/repos/OgarniaczSM/.venv/Scripts/python.exe -m compileall -q app tests
git diff --check
```

`test_archviz_core.py` uses temporary images and forbids live urllib requests.
It checks native lossless freezing, color copyback bounds and protection of
antialiased foreground, parent immutability and branches, completed-job
idempotence after restart, stale annotation SHA, explicit human approval,
unchanged last approved output, collision preflight, input/output separation,
narrow pen repair masks, external repair import and protected copyback,
dimension/base-version rejection, modified-frozen-parent rejection, and
diagnostic credential exclusion. Synthetic edits verify mechanics; they do
not prove Firefly or Gemini image quality.

## Actual application workflow

Use the real HTTP/Qt module and the same Python engine, without mocks:

1. Create a project with named input, work and output folders. Import all five
   Elektrovnia test copies. Verify their originals and native dimensions.
2. Select an exact image revision, draw an edge band and protected crossing,
   write its comment, save, switch frames and return. Reopen the project and
   verify marks/comments remain attached to the correct image hash.
3. Show before/after, fit, 100%, pan and native zoom. A small native crop must
   be displayed at its original pixel scale; a downsampled comparison sheet
   is insufficient evidence for edge quality.
4. Run a deterministic local correction via UI. Watch genuine job phases,
   inspect the immutable parent and result, and verify that completion did
   not approve or publish the candidate.
5. Export a Photoshop/Firefly repair kit, inspect target/mask/native context,
   import an edited test crop, and verify its dimensions, parent SHA and
   masked copyback. Do not label this an automatic Firefly API integration.
6. Independently preflight one genuine Gemini Pro HIGH edge job and one people
   job before the paid call. Confirm exact config/model in the real receipt.
   Root coordinates limited live calls; QA does not silently incur spending.
7. Inspect the actual returned final PNG, a full-frame view and all affected
   native joins. Verify no changes outside allowed areas or in protected
   people/reflections/antialiasing. Technical 0-diff is necessary but does
   not establish that an edited edge looks natural.
8. Approve an explicit test candidate, export JPG with the original basename,
   verify full decode and checksum, then revise it and confirm the unapproved
   revision cannot replace the previous approved JPG. Approve the revision,
   export again and verify old output backup is outside the delivery folder.
9. Exercise a recoverable error, reopen history/jobs, and inspect the Codex
   diagnostics bundle without secrets. Do not repeat an unknown paid request.
10. Recompute all production-asset SHA256 values and save the after-audit.

## Visual acceptance of edge repair

Explicitly reject or mark uncertain for a pale/dark fringe, jagged silhouette,
new hard rectangular seam, material bleeding between foreground/background,
changed leather color or texture, mismatched rug weave scale, repeated blur
patch, detached or embedded feet/legs, incorrect contact shadow, or distortion
of the protected neighboring object. Compare the result directly to the
frozen baseline and inspect both ends of the edited strip, not only its center.

A technically correct but visually weak generation remains an unapproved
candidate. The repair-kit route must remain usable for the user's existing
Photoshop/Firefly finishing workflow.

## Executed pilot, 22 October 2026

The isolated Elektrovnia pilot uses five frozen copies from the approved JPG
folder. Its work and output live under `_archviz_studio_pilot`, and its output
is `output_test`; no QA approval is a customer delivery approval.

The final suite passed 35 tests (26 core, 3 CLI, 3 live local HTTP,
3 existing updater tests), in the root's final full run (10.510 seconds).
Core checks also cover abandoned-worker recovery, paid-call
outcome uncertainty, immutable cached JPEG exports and lock recovery. A real
export checksum defect was found and fixed: repeated encoding had changed the
ICC timestamp; repeated export now reuses identical approved JPEG bytes.
Tint/warmth direction is checked independently of the implementation formula,
including zero outside/protected changes. CLI checks verify nonzero failure
exit, completed-job resume idempotence, and picker file IPC with no stdout.
Additional regressions passed: queued-only cancellation preserves
in-flight/unknown work, and failed-Comfy resume accepts only audited composition
overrides while preserving the original prompt, annotations and mask hashes.
The real cached-provider-output path was exercised with a small saved-result
fixture: failed Comfy composition followed by local resume reused exactly the
same output and receipt, without a network request or another budget charge.
After the generic `external_import` provenance label change, the three affected
external-import tests passed again. Compileall and diff whitespace checks passed.

Actual browser testing exercised numbered rectangle/protect comments, a local
color job through ComfyUI, revision branching, before/after, fit, native 100%,
pan, pencil comments that survived reload, a repair-kit roundtrip, explicit
test approval, JPG export, project reopen, duplicate import and diagnostics.
The external crop fixture was brightness-adjusted locally; this tests the
Photoshop/Firefly file handoff, not an actual Adobe generation.

An independent isolated service also exercised the actual new-project form,
input/work/output settings, import, settings changes, explicit reopen and a
complete service restart. All fields and the frozen native baseline persisted;
the budget was zero and no job was created. Evidence is under the pilot's
`intake_ui_test/intake_ui_report.json`. A real OgarniaczSM Qt/WebEngine window
loaded all five frames through the lazy internal module; its screenshot and
readback are `qa/qt_ogarniacz_archviz.png` and `.json`. No updater was started.

The genuine sofa/rug edge pilot used `gemini-3-pro-image`, explicit HIGH,
2K output and actual ComfyUI copyback. Independent review inspected both full
frames and separate native context and endpoint crops. The targeted jagged
contact became visibly cleaner without a pale fringe or changed weave scale.
The result remained a candidate. Its PNG SHA256 is
`8365af840f9a3aebf834ae46a90e2ceb59d2be66e2423581216900c62a2225c4`;
13,544 pixels changed, with zero outside the allowed band and zero inside
protection. This is acceptance of that pilot defect only, not a claim that all
preexisting full-frame defects have been repaired.

Exact artifacts and hashes are outside Git in
`Y:\__PROJECTS\Elektrovnia\wizki\codex_test_poprawek\_archviz_studio_pilot\qa`:

- `protected_sources_before.json`: original and approved-file intake hashes.
- `gui_color_003_check.json`, `gui_external_003_check.json`,
  `gui_workflow_003_qa.json`: actual browser checks, fixture disclosure and
  test-only export/diagnostic receipts.
- `live_edge_preflight.json`, `live_edge_final_qa.json`: independent semantic
  mask review and native final-image review, including exact image hashes.

The people pilot exposed the remaining source-matte weakness rather than hiding
it behind a technical PASS. Independent preflight rejected a stale mask sliver
over wood before the model call; the corrected package passed. The actual Pro
HIGH result was realistic and preserved the stroller/hands exactly, but retained
the old bob outline around a shorter haircut. It failed native visual QA.
A single free repair-kit import reused the already-paid, aligned provider image
and removed most of that contour. Small disconnected old-hair strokes remained
under the chin, so the repaired candidate also failed. Both versions were
explicitly rejected through the real UI and were not exported. No further model
call or flattened patch was attempted. This pilot does not establish reliable
automatic people-edge cleanup; the complete old matte/AA envelope still needs
careful review and, when necessary, the external repair workflow.

Final shared-service UI checks passed after restart: a disposable local queued
job was cancelled, and a real unavailable-Comfy failure was resumed with the
current local-composition control. The same job completed once; original options
and mask hashes remained unchanged, and the project remained at 2/2 paid calls.
The earlier test-approved 003 JPG retained identical bytes. History preserved
both rejected people versions and all accepted test/source revisions.

Final evidence is `gui_final_resume_cancel_check.json`,
`people033_final_qa.json`, `people033_cached_repair_final_qa.json`, and
`protected_sources_after.json`. All 12 protected original/approved files have
identical before/after SHA256 values. The delivery folder still contains exactly
its five preexisting approved JPGs; this module pilot did not change any of them.
