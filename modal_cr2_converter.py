"""
CR2 → JPEG Converter — Modal Serverless Endpoint
==================================================
Deploy:  modal deploy modal_cr2_converter.py
Test:    curl -X POST -F "file=@photo.cr2" YOUR_MODAL_URL/convert -o output.jpg

Pricing: ~$0.0002 per conversion (2s on a CPU container at ~$0.35/hr)
"""

import io
import os
import uuid
from pathlib import Path

import modal
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Modal image with all dependencies ────────────────────────────────────────
image = (
    modal.Image.debian_slim()
    .apt_install("libraw-dev")                          # required by rawpy
    .pip_install("fastapi", "rawpy", "Pillow", "python-multipart")
)

app = modal.App("cr2-converter", image=image)

# ── Free-tier rate limiting ──────────────────────────────────────────────────
# Simple in-memory counter per IP. Resets when Modal container cold-starts
# (acceptable for a free tool; upgrade to Redis if needed later).
from collections import defaultdict
import time

RATE_LIMIT = 10          # conversions per window per IP
RATE_WINDOW = 3600       # 1 hour
rate_store: dict[str, list[float]] = defaultdict(list)

def check_rate_limit(ip: str) -> bool:
    """Return True if request is within rate limit."""
    now = time.time()
    # Clean old entries
    rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]
    if len(rate_store[ip]) >= RATE_LIMIT:
        return False
    rate_store[ip].append(now)
    return True


# ── FastAPI app ──────────────────────────────────────────────────────────────

@app.function(
    allow_concurrent_inputs=10,         # handle up to 10 concurrent uploads
    container_idle_timeout=300,         # keep warm for 5 min between requests
)
@modal.asgi_app()
def web():
    fastapi_app = FastAPI(title="CR2 Converter", version="2.0.0")

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Conversion-Quality"],
    )

    @fastapi_app.get("/")
    async def health():
        return {"status": "ok", "service": "cr2-converter-modal"}

    @fastapi_app.post("/convert")
    async def convert(request: Request, file: UploadFile = File(...), quality: int = 85):
        """Convert a CR2 RAW file to JPEG and return it as a download."""
        # ── Validate file type ───────────────────────────────────────────
        filename = file.filename or "image.cr2"
        if not filename.lower().endswith(".cr2"):
            return JSONResponse(
                {"error": "Only .CR2 files are accepted"},
                status_code=400,
            )

        # ── Rate limit (per IP) ──────────────────────────────────────────
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
        if not check_rate_limit(client_ip):
            return JSONResponse(
                {
                    "error": "Free tier limit reached (10 conversions/hour). "
                             "Upgrade to Pro for unlimited conversions."
                },
                status_code=429,
            )

        # ── Clamp quality ────────────────────────────────────────────────
        quality = max(10, min(100, quality))

        # ── Write upload to temp file (rawpy needs a path) ───────────────
        safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        tmp_path = f"/tmp/{safe_name}"

        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        try:
            import rawpy
            from PIL import Image

            with rawpy.imread(tmp_path) as raw:
                rgb = raw.postprocess()

            img = Image.fromarray(rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            buf.seek(0)

            out_name = Path(filename).stem + ".jpg"

            return Response(
                content=buf.getvalue(),
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{out_name}"',
                    "X-Conversion-Quality": str(quality),
                },
            )

        except Exception as exc:
            return JSONResponse(
                {"error": f"Conversion failed: {exc}"},
                status_code=500,
            )

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return fastapi_app
