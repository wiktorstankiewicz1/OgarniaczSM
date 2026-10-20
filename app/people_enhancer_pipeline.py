"""
people_enhancer_pipeline.py
ComfyUI-based people enhancement pipeline for architectural visualizations.
Used by PeopleEnhancerWidget in OgarniaczSM.

Pipeline (3 passes):
  1. Detection: MM-GroundingDINO + SAM2 -> person masks filtered by height
  2. Structure lock: ControlNet Tile + denoise 0.32
  3. IPAdapter texture: PreciseStyleTransfer + denoise 0.36
  4. Face composite: blend original face back at 55% (top 30% of each person bbox only)
"""

import json, urllib.request, urllib.error, time, shutil, os
from pathlib import Path
from PIL import Image, ImageFilter
import numpy as np

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_INPUT = r"C:\ComfyUI\input"
COMFYUI_OUTPUT = r"C:\ComfyUI\output"
REFERENCE_IMAGE = "ipa_reference.png"   # must exist in ComfyUI\input\
MIN_HEIGHT_FRACTION = 0.075             # min person height as fraction of image height

REQUIRED_MODELS = {
    "checkpoint":   r"C:\ComfyUI\models\checkpoints\RealVisXL_V4.safetensors",
    "controlnet":   r"C:\ComfyUI\models\controlnet\xinsir_controlnet_union_sdxl_promax.safetensors",
    "ipadapter":    r"C:\ComfyUI\models\ipadapter\ip-adapter-plus_sdxl_vit-h.safetensors",
    "clip_vision":  r"C:\ComfyUI\models\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    "sam2":         r"C:\ComfyUI\models\sam2\sam2.1_hiera_large.safetensors",
}

def check_comfyui() -> dict:
    """Returns {'ok': bool, 'vram_free_gb': float, 'vram_total_gb': float, 'error': str}"""
    try:
        resp = urllib.request.urlopen(COMFYUI_URL + "/system_stats", timeout=3)
        data = json.loads(resp.read())
        devices = data.get("system", {}).get("devices", [])
        vram_free = vram_total = 0
        for d in devices:
            if d.get("type") == "cuda":
                vram_free  = d.get("vram_free", 0)  / 1e9
                vram_total = d.get("vram_total", 0) / 1e9
                break
        return {"ok": True, "vram_free_gb": round(vram_free, 1),
                "vram_total_gb": round(vram_total, 1), "error": ""}
    except Exception as e:
        return {"ok": False, "vram_free_gb": 0, "vram_total_gb": 0, "error": str(e)}

def check_models() -> dict:
    """Returns {'ok': bool, 'missing': [list of missing model keys]}"""
    missing = [k for k, p in REQUIRED_MODELS.items() if not Path(p).exists()]
    return {"ok": len(missing) == 0, "missing": missing}

def _submit(workflow: dict) -> str:
    payload = json.dumps({
        "prompt": workflow,
        "extra_data": {"extra_pnginfo": {}},
    }).encode("utf-8")
    req = urllib.request.Request(COMFYUI_URL + "/prompt", data=payload,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]

def _wait(prompt_id: str, timeout=900, progress_cb=None):
    """Poll until done. progress_cb(stage, pct) called periodically."""
    start = time.time()
    last_stage = ""
    while time.time() - start < timeout:
        resp = urllib.request.urlopen(COMFYUI_URL + "/history/" + prompt_id, timeout=10)
        h = json.loads(resp.read())
        if prompt_id in h:
            entry = h[prompt_id]
            s = entry.get("status", {}).get("status_str", "")
            if s == "success":
                return entry
            if s == "error":
                for m in entry["status"]["messages"]:
                    if m[0] == "execution_error":
                        raise RuntimeError("ComfyUI error in %s: %s" % (
                            m[1].get("node_type"), m[1].get("exception_message")))
                raise RuntimeError("ComfyUI job failed")
        time.sleep(4)
        if progress_cb:
            elapsed = int(time.time() - start)
            progress_cb("running", min(95, elapsed * 2))
    raise TimeoutError("ComfyUI job timed out after %ds" % timeout)

def _get_output_file(history_entry: dict) -> str | None:
    for node, out in history_entry.get("outputs", {}).items():
        for img in out.get("images", []):
            sub = img.get("subfolder", "")
            path = os.path.join(COMFYUI_OUTPUT, sub, img["filename"]) if sub else os.path.join(COMFYUI_OUTPUT, img["filename"])
            if os.path.exists(path):
                return path
    return None

def _build_workflow(input_filename: str, img_h: int) -> dict:
    """Build the full 3-pass ComfyUI workflow."""
    min_h_px = int(img_h * MIN_HEIGHT_FRACTION)
    return {
      "1":  {"class_type": "LoadImage", "inputs": {"image": input_filename, "upload": "image"}},
      "ref":{"class_type": "LoadImage", "inputs": {"image": REFERENCE_IMAGE, "upload": "image"}},
      "2":  {"class_type": "CheckpointLoaderSimple",
             "inputs": {"ckpt_name": "RealVisXL_V4.safetensors"}},
      "ipa_load": {"class_type": "IPAdapterUnifiedLoader",
                   "inputs": {"model": ["2", 0], "preset": "PLUS (high strength)"}},
      "20": {"class_type": "ControlNetLoader",
             "inputs": {"control_net_name": "xinsir_controlnet_union_sdxl_promax.safetensors"}},
      "21": {"class_type": "SetUnionControlNetType",
             "inputs": {"control_net": ["20", 0], "type": "tile"}},
      "3":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1],
             "text": "RAW photo, photorealistic person, real photograph, natural skin texture, pores, subsurface scattering, fabric texture, clothing wrinkles, hair strands, sharp focus, natural daylight, film grain, architectural lifestyle photography, candid, high detail"}},
      "4":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1],
             "text": "3d render, cgi, cartoon, smooth plastic skin, mannequin, anime, painting, blurry, low quality, deformed, extra limbs, watermark, text, oversaturated, toy, doll"}},
      "5":  {"class_type": "GroundingModelLoader",
             "inputs": {"model": "MM-GroundingDINO: Tiny O365+GoldG (50.4 mAP)", "keep_model_loaded": False}},
      "6":  {"class_type": "GroundingDetector",
             "inputs": {"model": ["5", 0], "image": ["1", 0],
                        "prompt": "person . pedestrian .", "confidence_threshold": 0.10,
                        "single_box_mode": False, "single_box_per_prompt_mode": False}},
      "7":  {"class_type": "DownLoadSAM2Model",
             "inputs": {"model": "sam2.1_hiera_large.safetensors",
                        "segmentor": "single_image", "device": "cuda", "precision": "fp16"}},
      "8":  {"class_type": "Sam2Segment",
             "inputs": {"sam2_model": ["7", 0], "image": ["1", 0], "keep_model_loaded": False,
                        "bboxes": ["6", 0], "individual_objects": True, "mask_threshold": 0.0,
                        "max_hole_area": 10.0, "max_sprinkle_area": 5.0}},
      "9":  {"class_type": "MaskToSEGS",
             "inputs": {"mask": ["8", 0], "combined": False, "crop_factor": 1.3,
                        "bbox_fill": False, "drop_size": 50, "contour_fill": False}},
      "13": {"class_type": "ImpactSEGSRangeFilter",
             "inputs": {"segs": ["9", 0], "target": "height", "mode": True,
                        "min_value": min_h_px, "max_value": 99999999}},
      "22a":{"class_type": "TilePreprocessor",
             "inputs": {"image": ["1", 0], "pyrUp_iters": 1, "resolution": 1024}},
      "23a":{"class_type": "ControlNetApplyAdvanced",
             "inputs": {"positive": ["3", 0], "negative": ["4", 0], "control_net": ["21", 0],
                        "image": ["22a", 0], "strength": 0.80, "start_percent": 0.0,
                        "end_percent": 0.85, "vae": ["2", 2]}},
      "10a":{"class_type": "DetailerForEach",
             "inputs": {"image": ["1", 0], "segs": ["13", 0], "model": ["2", 0],
                        "clip": ["2", 1], "vae": ["2", 2], "guide_size": 768,
                        "guide_size_for": True, "max_size": 1024, "seed": 42, "steps": 30,
                        "cfg": 4.5, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                        "positive": ["23a", 0], "negative": ["23a", 1], "denoise": 0.32,
                        "feather": 20, "noise_mask": True, "force_inpaint": True,
                        "wildcard": "", "cycle": 1, "inpaint_model": False,
                        "noise_mask_feather": 40, "tiled_encode": False, "tiled_decode": False}},
      "22b":{"class_type": "TilePreprocessor",
             "inputs": {"image": ["10a", 0], "pyrUp_iters": 1, "resolution": 1024}},
      "23b":{"class_type": "ControlNetApplyAdvanced",
             "inputs": {"positive": ["3", 0], "negative": ["4", 0], "control_net": ["21", 0],
                        "image": ["22b", 0], "strength": 0.55, "start_percent": 0.0,
                        "end_percent": 0.80, "vae": ["2", 2]}},
      "ipa_model": {"class_type": "IPAdapterPreciseStyleTransfer",
             "inputs": {"model": ["ipa_load", 0], "ipadapter": ["ipa_load", 1],
                        "image": ["ref", 0], "weight": 0.40, "style_boost": 1.0,
                        "combine_embeds": "concat", "start_at": 0.20, "end_at": 0.75,
                        "embeds_scaling": "K+V w/ C penalty"}},
      "10b":{"class_type": "DetailerForEach",
             "inputs": {"image": ["10a", 0], "segs": ["13", 0], "model": ["ipa_model", 0],
                        "clip": ["2", 1], "vae": ["2", 2], "guide_size": 768,
                        "guide_size_for": True, "max_size": 1024, "seed": 77, "steps": 28,
                        "cfg": 5.0, "sampler_name": "dpmpp_2m_sde", "scheduler": "karras",
                        "positive": ["23b", 0], "negative": ["23b", 1], "denoise": 0.36,
                        "feather": 20, "noise_mask": True, "force_inpaint": True,
                        "wildcard": "", "cycle": 1, "inpaint_model": False,
                        "noise_mask_feather": 40, "tiled_encode": False, "tiled_decode": False}},
      "11": {"class_type": "SaveImage",
             "inputs": {"images": ["10b", 0], "filename_prefix": "sm_people_enhanced"}},
    }

def _face_composite(orig_path: str, enhanced_path: str, output_path: str,
                    face_alpha: float = 0.55, feather: int = 30,
                    face_top_fraction: float = 0.30):
    """
    Blend original face pixels back over the enhanced image to restore eye/skin tone.

    Strategy:
      1. Find where the image changed (diff > threshold) -> person regions
      2. Label connected components to isolate individual people
      3. For each person, blend original back only in the TOP face_top_fraction
         of their bounding box -- that's where the face is, not the clothing
      4. Feather the blend mask edges so there's no hard line

    This matches what v11 did manually (measured face bbox + feathered blend at 0.55 alpha)
    but works automatically for any image without hardcoded coordinates.
    """
    try:
        from scipy import ndimage as ndi
    except ImportError:
        # scipy not available: fallback to no face composite (just copy enhanced)
        import shutil as _shutil
        _shutil.copy2(enhanced_path, output_path)
        return

    orig     = np.array(Image.open(orig_path).convert("RGB")).astype(float)
    enhanced = np.array(Image.open(enhanced_path).convert("RGB")).astype(float)
    result   = enhanced.copy()
    H, W     = result.shape[:2]

    # --- Step 1: find changed pixels (person regions) ---
    diff = np.abs(enhanced - orig).mean(axis=2)
    changed_mask = diff > 12   # tighter threshold to avoid blending background

    # Morphological close to merge nearby pixels into solid person blobs
    struct  = ndi.generate_binary_structure(2, 2)
    closed  = ndi.binary_closing(changed_mask, structure=struct, iterations=8)
    dilated = ndi.binary_dilation(closed, structure=struct, iterations=4)

    # --- Step 2: label connected components (= individual people) ---
    labeled, num_features = ndi.label(dilated)

    if num_features == 0:
        # Nothing changed -- save as-is
        Image.fromarray(enhanced.clip(0, 255).astype(np.uint8)).save(output_path)
        return

    # --- Step 3: for each person blob blend only the top face_top_fraction ---
    blend_mask = np.zeros((H, W), dtype=float)

    for label_id in range(1, num_features + 1):
        blob = (labeled == label_id)
        rows = np.where(blob.any(axis=1))[0]
        cols = np.where(blob.any(axis=0))[0]
        if len(rows) == 0 or len(cols) == 0:
            continue

        y_min, y_max = int(rows[0]), int(rows[-1])
        x_min, x_max = int(cols[0]), int(cols[-1])
        person_h = y_max - y_min

        # Skip tiny blobs (noise / balcony people)
        if person_h < H * 0.04:
            continue

        # Face zone = top face_top_fraction of the person bounding box
        face_y_max = y_min + int(person_h * face_top_fraction)
        face_y_max = min(face_y_max, y_max)

        # Build a feathered rectangle for the face zone
        for y in range(y_min, face_y_max + 1):
            dist_top    = y - y_min
            dist_bottom = face_y_max - y
            v_ramp = min(dist_top, dist_bottom, feather) / feather

            for x in range(x_min, x_max + 1):
                dist_left  = x - x_min
                dist_right = x_max - x
                h_ramp = min(dist_left, dist_right, feather) / feather

                alpha = v_ramp * h_ramp
                if alpha > blend_mask[y, x]:
                    blend_mask[y, x] = alpha

    # Scale by face_alpha
    blend_alpha = blend_mask * face_alpha

    # --- Step 4: apply blend ---
    for c in range(3):
        result[:, :, c] = (enhanced[:, :, c] * (1 - blend_alpha)
                           + orig[:, :, c]      * blend_alpha)

    Image.fromarray(result.clip(0, 255).astype(np.uint8)).save(output_path)

def estimate_time(img_w: int, img_h: int, person_count_estimate: int = 3) -> int:
    """Rough time estimate in seconds."""
    megapixels = (img_w * img_h) / 1e6
    base = 20  # detection + SAM2
    per_person_pass1 = 15 * max(1, megapixels / 10)
    per_person_pass2 = 12 * max(1, megapixels / 10)
    return int(base + person_count_estimate * (per_person_pass1 + per_person_pass2))

def free_vram():
    """Force ComfyUI to unload all models from VRAM before next job.
    This is critical to prevent device mismatch errors between jobs
    (GroundingDINO fails when a checkpoint is already loaded on CUDA).
    """
    try:
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        req = urllib.request.Request(
            COMFYUI_URL + "/free", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        time.sleep(3)  # wait for VRAM to actually free
    except Exception:
        time.sleep(2)  # still wait even if endpoint fails

def enhance_image(source_path: str, output_path: str, progress_cb=None) -> str:
    """
    Main entry point. Enhances people in source_path, saves to output_path.
    progress_cb(stage: str, pct: int) called throughout.
    Stages: 'preparing', 'detecting', 'pass1', 'pass2', 'face_fix', 'saving', 'done'
    Returns output_path on success, raises on error.
    """
    def progress(stage, pct):
        if progress_cb:
            progress_cb(stage, pct)

    progress("preparing", 0)
    free_vram()  # clear any stale model state from previous jobs
    time.sleep(1)

    # Load image and get dimensions
    img = Image.open(source_path)
    img_w, img_h = img.size

    # Copy to ComfyUI input folder
    src_name = Path(source_path).stem + "_sm_enhance" + Path(source_path).suffix
    comfy_input_path = os.path.join(COMFYUI_INPUT, src_name)
    shutil.copy2(source_path, comfy_input_path)

    # Ensure reference image exists
    ref_path = os.path.join(COMFYUI_INPUT, REFERENCE_IMAGE)
    if not os.path.exists(ref_path):
        raise FileNotFoundError("Reference image not found: %s\nRun setup to generate it." % ref_path)

    progress("detecting", 5)
    workflow = _build_workflow(src_name, img_h)

    progress("pass1", 10)
    prompt_id = _submit(workflow)

    # Poll with progress updates
    start = time.time()
    eta = estimate_time(img_w, img_h)
    while True:
        time.sleep(5)
        resp = urllib.request.urlopen(COMFYUI_URL + "/history/" + prompt_id, timeout=10)
        h = json.loads(resp.read())
        if prompt_id in h:
            entry = h[prompt_id]
            s = entry.get("status", {}).get("status_str", "")
            if s == "success":
                progress("face_fix", 85)
                enhanced_file = _get_output_file(entry)
                if not enhanced_file:
                    raise RuntimeError("ComfyUI completed but no output file found")
                break
            if s == "error":
                for m in entry["status"]["messages"]:
                    if m[0] == "execution_error":
                        raise RuntimeError("[%s] %s" % (
                            m[1].get("node_type"), m[1].get("exception_message")))
                raise RuntimeError("Job failed")
        elapsed = time.time() - start
        pct = min(84, 10 + int(elapsed / eta * 74))
        stage = "pass1" if pct < 50 else "pass2"
        progress(stage, pct)

    # Face composite pass (pure PIL + scipy, no ComfyUI)
    progress("face_fix", 88)
    _face_composite(source_path, enhanced_file, output_path, face_alpha=0.55, feather=30)

    progress("saving", 96)
    # Clean up temp input file
    try:
        os.remove(comfy_input_path)
    except Exception:
        pass

    progress("done", 100)
    return output_path
