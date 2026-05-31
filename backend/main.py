"""
CR2 → JPEG Conversion Backend
===============================
FastAPI service that accepts Canon CR2 RAW uploads and returns processed JPEGs.

Run locally:
  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import io
import os
import uuid
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CR2 Converter API", version="1.0.0")

# Allow the Next.js frontend (any origin during dev; tighten for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/")
async def health():
    return {"status": "ok", "service": "cr2-converter-backend"}


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    quality: int = 85,
):
    """Convert a CR2 RAW file to JPEG and return it."""
    # --- Validate -----------------------------------------------------------
    if not file.filename or not file.filename.lower().endswith(".cr2"):
        return Response(
            content='{"error":"Only .CR2 files are accepted"}',
            status_code=400,
            media_type="application/json",
        )

    if quality < 10 or quality > 100:
        quality = 85

    # --- Write upload to disk (rawpy needs a file path) --------------------
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    tmp_path = f"/tmp/{safe_name}"

    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        import rawpy
        from PIL import Image

        # Decode RAW sensor data → RGB numpy array
        with rawpy.imread(tmp_path) as raw:
            rgb = raw.postprocess()

        # Encode to JPEG
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)

        out_name = os.path.splitext(file.filename or "image")[0] + ".jpg"

        return Response(
            content=buf.getvalue(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{out_name}"',
                "X-Conversion-Quality": str(quality),
            },
        )

    except Exception as exc:
        return Response(
            content=f'{{"error":"Conversion failed: {exc}"}}',
            status_code=500,
            media_type="application/json",
        )

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/convert/batch")
async def convert_batch(
    files: list[UploadFile] = File(...),
    quality: int = 85,
):
    """Convert multiple CR2 files; returns a JSON list of base64 JPEGs."""
    import base64

    if quality < 10 or quality > 100:
        quality = 85

    results = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".cr2"):
            results.append({
                "filename": file.filename,
                "error": "Not a .CR2 file",
            })
            continue

        safe_name = f"{uuid.uuid4().hex}_{file.filename}"
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

            out_name = os.path.splitext(file.filename or "image")[0] + ".jpg"
            results.append({
                "filename": out_name,
                "data": base64.b64encode(buf.getvalue()).decode("utf-8"),
                "size_bytes": len(buf.getvalue()),
            })
        except Exception as exc:
            results.append({
                "filename": file.filename,
                "error": str(exc),
            })
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return {"results": results, "quality": quality}
