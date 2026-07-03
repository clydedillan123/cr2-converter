"""
Photo Toolkit — Modal Serverless Endpoint
==========================================
Free tools for real estate photographers, all running on Modal.

Deploy:  modal deploy modal_photo_toolkit.py
Endpoints:
  POST /convert/raw       Universal RAW → JPEG  (CR2, NEF, ARW, DNG, RAF, ORF, RW2)
  POST /convert/batch     Multiple RAW → zip of JPEGs
  POST /convert/heic      HEIC → JPEG
  POST /convert/resize    JPEG resize (MLS-ready)
  POST /convert/compress  JPEG compressor
  POST /convert/hdr       HDR merge (3–5 bracketed shots → balanced JPEG)
  POST /convert/cull      Exposure auto-culler (histogram analysis per frame)
  POST /organize/brackets Group + validate HDR bracket sets (EXIF-only, no decode)
  POST /inspect/mls       MLS preflight compliance check (dimensions, sRGB, GPS, etc.)

Free tier: 10 conversions/hour/IP across all endpoints.
"""

import io
import os
import time
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path

import modal
from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Modal image ──────────────────────────────────────────────────────────────
image = (
    modal.Image.debian_slim()
    .apt_install("libraw-dev", "libheif-dev")
    .pip_install(
        "fastapi",
        "rawpy",
        "Pillow",
        "python-multipart",
        "pillow-heif",              # HEIC/HEIF support for Pillow
        "opencv-python-headless",   # HDR merge + image alignment
        "numpy",
        "exifread",                 # EXIF metadata for bracket organizer (JPEG + RAW)
    )
    .env({"TOOLKIT_VERSION": "1.1.2"})
)

app = modal.App("photo-toolkit", image=image)

# ── Rate limiting (shared across all endpoints) ──────────────────────────────
RATE_LIMIT = 10          # conversions per window per IP
RATE_WINDOW = 3600       # 1 hour
rate_store: dict[str, list[float]] = defaultdict(list)

# Valid RAW extensions that rawpy can handle
RAW_EXTENSIONS = {".cr2", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw", ".cr3"}


def check_rate_limit(ip: str) -> bool:
    """Return True if request is within rate limit."""
    now = time.time()
    rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]
    if len(rate_store[ip]) >= RATE_LIMIT:
        return False
    rate_store[ip].append(now)
    return True


def rate_limit_response() -> JSONResponse:
    return JSONResponse(
        {
            "error": "Free tier limit reached (10 conversions/hour). "
                     "Upgrade to Pro for unlimited conversions."
        },
        status_code=429,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for",
               request.client.host if request.client else "unknown")


def clamp_quality(q: int) -> int:
    return max(10, min(100, q))


def raw_to_jpeg_bytes(file_path: str, quality: int = 92) -> bytes:
    """Decode any RAW file via rawpy → JPEG bytes."""
    import rawpy
    from PIL import Image

    with rawpy.imread(file_path) as raw:
        rgb = raw.postprocess()
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf.getvalue()


def heic_to_jpeg_bytes(data: bytes, quality: int = 92) -> bytes:
    """Decode HEIC → JPEG bytes."""
    from PIL import Image

    # pillow-heif registers itself as a Pillow plugin on import
    import pillow_heif
    pillow_heif.register_heif_opener()

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf.getvalue()


def resize_jpeg_bytes(data: bytes, max_size: int = 1024, quality: int = 85) -> bytes:
    """Resize JPEG so longest edge ≤ max_size, maintaining aspect ratio."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    w, h = img.size
    longest = max(w, h)
    if longest > max_size:
        ratio = max_size / longest
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf.getvalue()


def compress_jpeg_bytes(data: bytes, quality: int = 70) -> bytes:
    """Re-encode JPEG at lower quality."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    buf.seek(0)
    return buf.getvalue()


def hdr_merge_bytes(files_data: list[bytes], tone_mapper: str = "reinhard") -> bytes:
    """
    Merge 3–5 bracketed exposures into a balanced HDR JPEG.
    Uses OpenCV: align → estimate CRF → merge → tone map → encode.
    """
    import cv2
    import numpy as np

    if len(files_data) < 3:
        raise ValueError("Need at least 3 bracketed exposures")
    if len(files_data) > 7:
        raise ValueError("Maximum 7 exposures")

    # Decode images
    images = []
    for data in files_data:
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode one of the uploaded images")
        # Ensure 3-channel BGR
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        images.append(img)

    # Resize all images to match the smallest dimensions
    min_h = min(img.shape[0] for img in images)
    min_w = min(img.shape[1] for img in images)
    images = [cv2.resize(img, (min_w, min_h)) for img in images]

    # Convert to float for HDR merge
    images_float = [img.astype(np.float32) / 255.0 for img in images]

    # Merge exposures with Mertens (no calibration or alignment needed)
    merge = cv2.createMergeMertens()
    hdr = merge.process(images_float)

    # Tone map HDR → LDR
    if tone_mapper == "mantiuk":
        tonemap = cv2.createTonemapMantiuk(gamma=1.0, scale=0.85, saturation=1.2)
    else:
        # Reinhard — natural, realistic look (default for real estate)
        tonemap = cv2.createTonemapReinhard(gamma=1.0, intensity=0.0, light_adapt=1.0, color_adapt=0.0)

    ldr = tonemap.process(hdr)

    # Convert to 8-bit and encode as JPEG
    ldr_8bit = np.clip(ldr * 255, 0, 255).astype(np.uint8)
    success, encoded = cv2.imencode(".jpg", ldr_8bit, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not success:
        raise ValueError("Failed to encode HDR result")

    return encoded.tobytes()


def exposure_score_bytes(data: bytes) -> tuple[int, str, float]:
    """
    Analyze image exposure via histogram.
    Returns (score 0–100, grade, mean_brightness 0–255).

    Score ranges:
      0–30  → dark (underexposed)
      31–50 → slightly dark
      51–70 → good exposure
      71–85 → slightly bright
      86–100 → blown (overexposed)

    Grade is one of: "dark", "good", "blown"
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))

    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten()
    total = float(np.sum(hist))
    if total == 0:
        raise ValueError("Empty image")

    shadows = np.sum(hist[0:64]) / total       # 0–63
    midtones = np.sum(hist[64:192]) / total     # 64–191
    highlights = np.sum(hist[192:256]) / total  # 192–255

    # Compute a weighted exposure score
    # Low mean + high shadows → dark.  High mean + high highlights → blown.
    # Ideal: bright but not clipped, good midtone presence.

    if mean_brightness < 50 and shadows > 0.6:
        score = round(max(0, mean_brightness / 50 * 25))
        grade = "dark"
    elif mean_brightness > 200 and highlights > 0.4:
        score = round(85 + min(15, (mean_brightness - 200) / 55 * 15))
        grade = "blown"
    elif mean_brightness < 80:
        score = round(25 + (mean_brightness - 50) / 30 * 25)
        grade = "dark" if score < 50 else "good"
    elif mean_brightness > 180:
        score = round(70 + (mean_brightness - 180) / 75 * 30)
        grade = "blown" if score > 70 else "good"
    else:
        # Well-exposed sweet spot (80–180 mean)
        # Score penalized by extreme shadow/highlight clipping
        clip_penalty = max(0, (shadows - 0.3)) * 20 + max(0, (highlights - 0.25)) * 30
        score = round(max(50, 75 - clip_penalty))
        grade = "good" if score >= 50 else "dark"

    return score, grade, mean_brightness


# ── Bracket organizer helpers ────────────────────────────────────────────────
# EXIF-only: groups bracketed exposures into sets and validates each set.
# No full RAW decode — reads metadata via exifread (works on JPEG + most RAW).

def _first_val(tag):
    """Return the first value of an exifread tag, or None."""
    if tag is None:
        return None
    vals = getattr(tag, "values", None)
    if vals is None:
        return None
    if isinstance(vals, (list, tuple)):
        return vals[0] if vals else None
    return vals


def _tag_num(tags, *names):
    """First numeric value found under any of the named EXIF tags."""
    from fractions import Fraction
    for n in names:
        v = _first_val(tags.get(n))
        if v is None:
            continue
        if isinstance(v, Fraction):
            return float(v)
        if isinstance(v, (int, float)):
            return float(v)
        if hasattr(v, "numerator") and hasattr(v, "denominator") and v.denominator:
            return float(v.numerator) / float(v.denominator)
        if isinstance(v, str):
            s = v.strip()
            if "/" in s:
                a, b = s.split("/", 1)
                try:
                    return float(a) / float(b)
                except ValueError:
                    return None
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _tag_str(tags, *names):
    """First string value found under any of the named EXIF tags."""
    for n in names:
        v = _first_val(tags.get(n))
        if v is None:
            continue
        if isinstance(v, str):
            return v.strip()
        return str(v)
    return None


def read_exif(data: bytes) -> dict | None:
    """
    Read bracket-relevant EXIF from image bytes.
    Works on JPEG/TIFF/RAW via exifread; falls back to Pillow for the
    capture timestamp on JPEG/TIFF. Returns None when nothing is readable.
    """
    import exifread
    from datetime import datetime

    tags = {}
    try:
        with io.BytesIO(data) as f:
            tags = exifread.process_file(f, details=False) or {}
    except Exception:
        tags = {}

    dt_str = _tag_str(tags, "EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime")
    timestamp = None
    if dt_str:
        try:
            timestamp = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            timestamp = None

    # Pillow fallback for timestamp (JPEG/TIFF) when exifread found nothing
    if timestamp is None:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            exif = img.getexif() if hasattr(img, "getexif") else None
            if exif:
                s = exif.get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
                if s:
                    try:
                        timestamp = datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        timestamp = None
        except Exception:
            pass

    if timestamp is None and not tags:
        return None

    ev = _tag_num(tags, "EXIF ExposureCompensation", "EXIF ExposureBiasValue")
    iso = _tag_num(tags, "EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity", "Image ISOSpeedRatings")
    aperture = _tag_num(tags, "EXIF FNumber", "EXIF ApertureValue")
    focal = _tag_num(tags, "EXIF FocalLength")
    exposure_time = _tag_num(tags, "EXIF ExposureTime")

    shutter = None
    if exposure_time is not None:
        from fractions import Fraction
        fr = Fraction(exposure_time).limit_denominator(1_000_000)
        shutter = f"{fr.numerator}s" if fr.denominator == 1 else f"{fr.numerator}/{fr.denominator}s"

    return {
        "timestamp": timestamp,
        "ev": ev,
        "iso": int(iso) if iso is not None else None,
        "aperture": aperture,
        "focal": focal,
        "shutter": shutter,
    }


def _drift_issue(frames: list[dict], field: str, label: str, fmt) -> str | None:
    """Return an issue string if a setting changed within the set, else None."""
    vals = [f["exif"][field] for f in frames if f["exif"] and f["exif"][field] is not None]
    uniq = sorted(set(round(v, 2) for v in vals))
    if len(uniq) > 1:
        return f"{label} changed within set (" + " → ".join(fmt(v) for v in uniq) + ")"
    return None


def organize_brackets(metas: list[dict], gap_seconds: float = 2.0) -> dict:
    """
    Group bracketed exposures by capture-time gap, then validate each set.
    `metas`: [{"filename": str, "exif": dict | None}].
    """
    from datetime import datetime

    known = [m for m in metas if m["exif"] and m["exif"]["timestamp"]]
    no_exif = [{"filename": m["filename"]} for m in metas if not (m["exif"] and m["exif"]["timestamp"])]
    known.sort(key=lambda m: m["exif"]["timestamp"])

    groups_raw: list[list[dict]] = []
    singles: list[dict] = []
    current: list[dict] = []

    for m in known:
        if not current:
            current = [m]
            continue
        gap = (m["exif"]["timestamp"] - current[-1]["exif"]["timestamp"]).total_seconds()
        if gap <= gap_seconds:
            current.append(m)
        else:
            if len(current) >= 2:
                groups_raw.append(current)
            else:
                singles.append(current[0])
            current = [m]
    if current:
        if len(current) >= 2:
            groups_raw.append(current)
        else:
            singles.append(current[0])

    groups_out = []
    valid_count = 0
    flagged_count = 0

    for i, frames in enumerate(groups_raw):
        label = f"Bracket {chr(ord('A') + i)}" if i < 26 else f"Bracket {i + 1}"
        # Order by EV ascending (None last); fallback keeps capture order.
        frames_sorted = sorted(
            frames,
            key=lambda m: (m["exif"]["ev"] is None, m["exif"]["ev"] if m["exif"]["ev"] is not None else float("inf")),
        )
        issues: list[str] = []
        count = len(frames_sorted)

        if count not in (3, 5, 7):
            issues.append(f"Incomplete bracket set — {count} frames (expected 3, 5, or 7)")

        evs = [f["exif"]["ev"] for f in frames_sorted if f["exif"]["ev"] is not None]
        # Duplicate exposures
        seen: dict[float, int] = {}
        for e in evs:
            seen[e] = seen.get(e, 0) + 1
        dups = [e for e, c in seen.items() if c > 1]
        if dups:
            issues.append("Duplicate exposure (" + ", ".join(f"EV {_ev_str(e)}" for e in dups) + ")")

        # Missing intermediate exposures (only meaningful for monotonic EV runs)
        if len(evs) >= 3:
            sev = sorted(evs)
            diffs = [sev[j + 1] - sev[j] for j in range(len(sev) - 1)]
            pos = [d for d in diffs if d > 0]
            if pos:
                step = sum(pos) / len(pos)
                missing_at = [sev[j + 1] for j, d in enumerate(diffs) if d > step * 1.6 and d > 0.5]
                if missing_at:
                    issues.append("Possible missing exposure near EV " + ", ".join(_ev_str(m) for m in missing_at))

        # Drift in aperture / ISO / focal length
        for field, lbl, fmt in (
            ("aperture", "Aperture", lambda v: f"f/{v:g}"),
            ("iso", "ISO", lambda v: f"{int(v)}"),
            ("focal", "Focal length", lambda v: f"{v:g}mm"),
        ):
            issue = _drift_issue(frames_sorted, field, lbl, fmt)
            if issue:
                issues.append(issue)

        valid = not issues
        if valid:
            valid_count += 1
        else:
            flagged_count += 1

        t0 = frames_sorted[0]["exif"]["timestamp"]
        tN = frames_sorted[-1]["exif"]["timestamp"]
        groups_out.append({
            "label": label,
            "valid": valid,
            "count": count,
            "start_time": t0.isoformat(),
            "end_time": tN.isoformat(),
            "span_seconds": round((tN - t0).total_seconds(), 2),
            "issues": issues,
            "frames": [{
                "filename": f["filename"],
                "ev": f["exif"]["ev"],
                "shutter": f["exif"]["shutter"],
                "iso": f["exif"]["iso"],
                "aperture": f["exif"]["aperture"],
                "focal": f["exif"]["focal"],
                "timestamp": f["exif"]["timestamp"].isoformat(),
            } for f in frames_sorted],
        })

    return {
        "groups": groups_out,
        "singles": [{"filename": s["filename"], "timestamp": s["exif"]["timestamp"].isoformat()} for s in singles],
        "no_exif": no_exif,
        "summary": {
            "total_sets": len(groups_out),
            "valid_sets": valid_count,
            "flagged_sets": flagged_count,
            "singles": len(singles),
            "no_exif": len(no_exif),
            "total_files": len(metas),
        },
    }


def _ev_str(v: float) -> str:
    return f"{'+' if v >= 0 else ''}{v:g}"


def _form_bool(v) -> bool:
    """Parse a multipart form value into a bool (robust across 'true'/'1'/'yes')."""
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ── MLS preflight inspection ─────────────────────────────────────────────────
# Deterministic, server-side compliance checks. No watermark/staging detection
# (not reliably solvable) — only measurable technical properties.

def inspect_image(data: bytes, filename: str, req: dict) -> dict:
    """Inspect one image against MLS-style technical requirements."""
    from PIL import Image

    file_kb = round(len(data) / 1024, 1)
    issues: list[str] = []

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        return {
            "filename": filename, "error": f"Unreadable: {exc}",
            "issues": ["Unreadable image"], "passed": False, "needs_correction": False,
        }

    w, h = img.size
    aspect = round(w / h, 3) if h else 0
    fmt = (img.format or "").upper()

    # sRGB detection via ICC profile name (ImageCms); None when no profile embedded
    icc = img.info.get("icc_profile")
    srgb = None
    if icc:
        try:
            from PIL import ImageCms
            name = ImageCms.getProfileName(ImageCms.ImageCmsProfile(io.BytesIO(icc)))
            srgb = "srgb" in (name or "").lower()
        except Exception:
            srgb = False

    # Orientation
    exif = img.getexif() if hasattr(img, "getexif") else None
    orientation = exif.get(274) if exif else None

    # GPS — try Pillow, then fall back to exifread (belt and suspenders)
    has_gps = False
    if exif:
        try:
            has_gps = bool(exif.get_ifd(0x8825)) or (34853 in exif)
        except Exception:
            has_gps = 34853 in exif
    if not has_gps:
        try:
            import exifread as _exr
            with io.BytesIO(data) as _fh:
                _tags = _exr.process_file(_fh, details=False) or {}
            has_gps = any(k.startswith("GPS") for k in _tags)
        except Exception:
            pass

    # Compression heuristic (bytes per pixel)
    bpp = len(data) / (w * h) if w and h else 0

    # Exposure (reuse histogram grade)
    grade = None
    try:
        _score, grade, _mean = exposure_score_bytes(data)
    except Exception:
        grade = None

    # ── evaluate against requirements ──
    max_edge = req.get("max_edge")
    if max_edge and max(w, h) > max_edge:
        issues.append(f"Over max size ({max(w, h)}px > {max_edge}px)")
    max_file_mb = req.get("max_file_mb")
    if max_file_mb and (len(data) / (1024 * 1024)) > max_file_mb:
        issues.append(f"File too large ({file_kb} KB > {max_file_mb} MB)")
    if req.get("require_jpeg") and fmt != "JPEG":
        issues.append(f"Not JPEG ({fmt})")
    if req.get("require_srgb") and srgb is False:
        issues.append("Not sRGB colour profile")
    if req.get("require_no_gps") and has_gps:
        issues.append("GPS metadata present")
    if orientation and orientation != 1:
        issues.append(f"Orientation tag set ({orientation}) — auto-fixed on export")

    needs_correction = grade in ("dark", "blown") if grade else False

    return {
        "filename": filename,
        "width": w,
        "height": h,
        "aspect": aspect,
        "file_kb": file_kb,
        "format": fmt,
        "srgb": srgb,            # True / False / None
        "orientation": orientation,
        "has_gps": has_gps,
        "bpp": round(bpp, 3),
        "exposure": grade,       # "good" / "dark" / "blown" / None
        "needs_correction": needs_correction,
        "issues": issues,
        "passed": len(issues) == 0,
    }


# ── FastAPI app ──────────────────────────────────────────────────────────────

@app.function(
    scaledown_window=300,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def web():
    fastapi_app = FastAPI(title="Photo Toolkit", version="2.0.0")

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Conversion-Quality", "X-Original-Size", "X-New-Size"],
    )

    @fastapi_app.get("/")
    async def health():
        return {"status": "ok", "service": "photo-toolkit-modal", "endpoints": [
            "POST /convert/raw",
            "POST /convert/batch",
            "POST /convert/heic",
            "POST /convert/resize",
            "POST /convert/compress",
            "POST /convert/hdr",
            "POST /convert/cull",
            "POST /organize/brackets",
            "POST /inspect/mls",
        ]}

    # ═══════════════════════════════════════════════════════════════════════
    # 1. Universal RAW → JPEG
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/raw")
    async def convert_raw(request: Request, file: UploadFile = File(...), quality: int = 92):
        """Convert any RAW format (CR2, NEF, ARW, DNG, etc.) to JPEG."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        filename = file.filename or "image.raw"
        ext = Path(filename).suffix.lower()
        if ext not in RAW_EXTENSIONS:
            return JSONResponse(
                {"error": f"Unsupported format '{ext}'. "
                          f"Accepted: {', '.join(sorted(RAW_EXTENSIONS))}"},
                status_code=400,
            )

        quality = clamp_quality(quality)
        tmp_path = f"/tmp/{uuid.uuid4().hex}_{Path(filename).name}"

        try:
            with open(tmp_path, "wb") as f:
                f.write(await file.read())

            jpeg_data = raw_to_jpeg_bytes(tmp_path, quality)
            out_name = Path(filename).stem + ".jpg"

            return Response(
                content=jpeg_data,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{out_name}"',
                    "X-Conversion-Quality": str(quality),
                    "X-Original-Size": str(os.path.getsize(tmp_path)),
                    "X-New-Size": str(len(jpeg_data)),
                },
            )
        except Exception as exc:
            return JSONResponse({"error": f"RAW conversion failed: {exc}"}, status_code=500)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. Batch RAW → zip of JPEGs
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/batch")
    async def convert_batch(
        request: Request,
        files: list[UploadFile] = File(...),
        quality: int = 92,
    ):
        """Convert multiple RAW files → zip of JPEGs. Max 20 files."""
        client_ip = get_client_ip(request)
        # Batch counts as 1 conversion against the rate limit
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        if len(files) > 20:
            return JSONResponse(
                {"error": "Maximum 20 files per batch."},
                status_code=400,
            )
        if len(files) == 0:
            return JSONResponse({"error": "No files provided."}, status_code=400)

        quality = clamp_quality(quality)
        zip_buf = io.BytesIO()
        results: list[dict] = []

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                fname = f.filename or "image.raw"
                ext = Path(fname).suffix.lower()

                if ext not in RAW_EXTENSIONS:
                    results.append({"filename": fname, "error": f"Unsupported format: {ext}"})
                    continue

                tmp_path = f"/tmp/{uuid.uuid4().hex}_{Path(fname).name}"
                try:
                    with open(tmp_path, "wb") as tmp:
                        tmp.write(await f.read())

                    jpeg_data = raw_to_jpeg_bytes(tmp_path, quality)
                    out_name = Path(fname).stem + ".jpg"
                    zf.writestr(out_name, jpeg_data)
                    results.append({"filename": out_name, "status": "ok"})
                except Exception as exc:
                    results.append({"filename": fname, "error": str(exc)})
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        zip_buf.seek(0)
        return Response(
            content=zip_buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="converted_batch.zip"',
                "X-Results": str(results),
            },
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 3. HEIC → JPEG
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/heic")
    async def convert_heic(request: Request, file: UploadFile = File(...), quality: int = 92):
        """Convert HEIC/HEIF to JPEG."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        filename = file.filename or "image.heic"
        ext = Path(filename).suffix.lower()
        if ext not in {".heic", ".heif", ".hif"}:
            return JSONResponse(
                {"error": f"Expected .HEIC/.HEIF file, got '{ext}'"},
                status_code=400,
            )

        quality = clamp_quality(quality)
        data = await file.read()

        try:
            jpeg_data = heic_to_jpeg_bytes(data, quality)
            out_name = Path(filename).stem + ".jpg"

            return Response(
                content=jpeg_data,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{out_name}"',
                    "X-Conversion-Quality": str(quality),
                    "X-Original-Size": str(len(data)),
                    "X-New-Size": str(len(jpeg_data)),
                },
            )
        except Exception as exc:
            return JSONResponse({"error": f"HEIC conversion failed: {exc}"}, status_code=500)

    # ═══════════════════════════════════════════════════════════════════════
    # 4. MLS Resizer
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/resize")
    async def convert_resize(
        request: Request,
        file: UploadFile = File(...),
        max_size: int = Form(1024),
        quality: int = Form(85),
    ):
        """Resize a JPEG so the longest edge ≤ max_size (default 1024px for MLS)."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        max_size = max(200, min(4096, max_size))
        quality = clamp_quality(quality)
        data = await file.read()

        try:
            resized = resize_jpeg_bytes(data, max_size, quality)
            out_name = Path(file.filename or "image.jpg").stem + f"_{max_size}px.jpg"

            return Response(
                content=resized,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{out_name}"',
                    "X-Original-Size": str(len(data)),
                    "X-New-Size": str(len(resized)),
                    "X-Max-Size": str(max_size),
                },
            )
        except Exception as exc:
            return JSONResponse({"error": f"Resize failed: {exc}"}, status_code=500)

    # ═══════════════════════════════════════════════════════════════════════
    # 5. JPEG Compressor
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/compress")
    async def convert_compress(
        request: Request,
        file: UploadFile = File(...),
        quality: int = Form(70),
    ):
        """Compress a JPEG by re-encoding at a lower quality level."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        quality = clamp_quality(quality)
        data = await file.read()

        try:
            compressed = compress_jpeg_bytes(data, quality)
            out_name = Path(file.filename or "image.jpg").stem + "_compressed.jpg"
            savings = len(data) - len(compressed)
            pct = round(savings / len(data) * 100, 1) if len(data) > 0 else 0

            return Response(
                content=compressed,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{out_name}"',
                    "X-Original-Size": str(len(data)),
                    "X-New-Size": str(len(compressed)),
                    "X-Savings-Bytes": str(savings),
                    "X-Savings-Pct": str(pct),
                },
            )
        except Exception as exc:
            return JSONResponse({"error": f"Compression failed: {exc}"}, status_code=500)

    # ═══════════════════════════════════════════════════════════════════════
    # 6. HDR Merge
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/hdr")
    async def convert_hdr(
        request: Request,
        files: list[UploadFile] = File(...),
        tone: str = Form("reinhard"),
    ):
        """Merge 3–5 bracketed exposures into a balanced HDR JPEG."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        if len(files) < 3:
            return JSONResponse(
                {"error": "Need at least 3 bracketed exposures (underexposed, normal, overexposed)."},
                status_code=400,
            )
        if len(files) > 7:
            return JSONResponse({"error": "Maximum 7 exposures per merge."}, status_code=400)

        if tone not in ("reinhard", "mantiuk"):
            tone = "reinhard"

        try:
            # Read all files into memory
            data = [await f.read() for f in files]

            merged = hdr_merge_bytes(data, tone)

            return Response(
                content=merged,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": 'attachment; filename="hdr_merged.jpg"',
                    "X-Tone-Mapper": tone,
                    "X-Exposures-Merged": str(len(files)),
                },
            )
        except Exception as exc:
            return JSONResponse({"error": f"HDR merge failed: {exc}"}, status_code=500)

    # ═══════════════════════════════════════════════════════════════════════
    # 7. Exposure Auto-Culler
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/convert/cull")
    async def convert_cull(
        request: Request,
        files: list[UploadFile] = File(...),
    ):
        """Analyze exposure for a batch of images. Returns per-image scores + grades."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        if len(files) == 0:
            return JSONResponse({"error": "No files provided."}, status_code=400)
        if len(files) > 30:
            return JSONResponse({"error": "Maximum 30 files per batch."}, status_code=400)

        results: list[dict] = []
        for f in files:
            fname = f.filename or "unknown"
            try:
                data = await f.read()
                score, grade, mean_brightness = exposure_score_bytes(data)
                results.append({
                    "filename": fname,
                    "score": score,
                    "grade": grade,
                    "meanBrightness": round(mean_brightness, 1),
                })
            except Exception as exc:
                results.append({"filename": fname, "error": str(exc)})

        # Summary counts
        blown = sum(1 for r in results if r.get("grade") == "blown")
        dark = sum(1 for r in results if r.get("grade") == "dark")
        good = sum(1 for r in results if r.get("grade") == "good")
        error_count = sum(1 for r in results if "error" in r)

        return JSONResponse({
            "results": results,
            "summary": {"blown": blown, "dark": dark, "good": good, "errors": error_count},
        })

    # ═══════════════════════════════════════════════════════════════════════
    # 8. HDR Bracket Organizer & Validator
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/organize/brackets")
    async def organize_brackets_ep(
        request: Request,
        files: list[UploadFile] = File(...),
        gap: float = Form(2.0),
    ):
        """Group bracketed exposures into sets and validate each set (EXIF-only)."""
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        if len(files) == 0:
            return JSONResponse({"error": "No files provided."}, status_code=400)
        if len(files) > 60:
            return JSONResponse({"error": "Maximum 60 files per batch."}, status_code=400)

        gap = max(1.0, min(5.0, float(gap)))

        metas = []
        for f in files:
            fname = f.filename or "image"
            try:
                data = await f.read()
                exif = read_exif(data)
            except Exception:
                exif = None
            metas.append({"filename": fname, "exif": exif})

        try:
            result = organize_brackets(metas, gap)
        except Exception as exc:
            return JSONResponse({"error": f"Organize failed: {exc}"}, status_code=500)

        return JSONResponse(result)

    # ═══════════════════════════════════════════════════════════════════════
    # 9. MLS Preflight Inspector
    # ═══════════════════════════════════════════════════════════════════════

    @fastapi_app.post("/inspect/mls")
    async def inspect_mls(
        request: Request,
        files: list[UploadFile] = File(...),
        max_edge: int = Form(2048),
        max_file_mb: float = Form(5.0),
        require_srgb: str = Form("true"),
        require_jpeg: str = Form("true"),
        require_no_gps: str = Form("true"),
        require_sequential: str = Form("true"),
    ):
        """Inspect a folder against MLS-style technical requirements."""
        import re

        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            return rate_limit_response()

        if len(files) == 0:
            return JSONResponse({"error": "No files provided."}, status_code=400)
        if len(files) > 30:
            return JSONResponse({"error": "Maximum 30 files per batch."}, status_code=400)

        req = {
            "max_edge": max(200, min(8192, int(max_edge))),
            "max_file_mb": max(0.1, float(max_file_mb)),
            "require_srgb": _form_bool(require_srgb),
            "require_jpeg": _form_bool(require_jpeg),
            "require_no_gps": _form_bool(require_no_gps),
            "require_sequential": _form_bool(require_sequential),
        }

        results: list[dict] = []
        for f in files:
            fname = f.filename or "image"
            try:
                data = await f.read()
                results.append(inspect_image(data, fname, req))
            except Exception as exc:
                results.append({
                    "filename": fname, "error": str(exc),
                    "issues": ["Inspection failed"], "passed": False, "needs_correction": False,
                })

        # Sequential naming check (folder-level)
        naming = {"ok": True, "notes": []}
        if req["require_sequential"]:
            nums = []
            for r in results:
                m = re.search(r"(\d+)", r.get("filename", ""))
                if m:
                    nums.append(int(m.group(1)))
            if nums:
                dup = sorted({n for n in nums if nums.count(n) > 1})
                present = set(nums)
                missing = [n for n in range(min(nums), max(nums) + 1) if n not in present]
                if dup:
                    naming["notes"].append("Duplicate numbers: " + ", ".join(map(str, dup)))
                if missing:
                    naming["notes"].append("Missing numbers: " + ", ".join(map(str, missing)))
                if dup or missing:
                    naming["ok"] = False
            else:
                naming["notes"].append("No numeric pattern found in filenames")

        passed = sum(1 for r in results if r.get("passed") and not r.get("error"))
        failed = len(results) - passed
        needs_correction = sum(1 for r in results if r.get("needs_correction"))

        return JSONResponse({
            "results": results,
            "naming": naming,
            "requirements": req,
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "needs_correction": needs_correction,
            },
        })

    return fastapi_app
