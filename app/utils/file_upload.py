import io
import os
import uuid
from typing import Optional
import aiofiles
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile, HTTPException
from app.config import settings

IMAGE_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_ALLOWED_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
SAFE_FOLDERS = {"general", "products", "product_videos", "categories"}
IMAGE_EXTENSIONS = {"jpeg", "jpg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}


def _normalize_folder(folder: str) -> str:
    normalized = os.path.basename(folder.strip())
    if normalized not in SAFE_FOLDERS:
        raise HTTPException(status_code=400, detail="Invalid upload folder")
    return normalized


def _validate_image(contents: bytes) -> None:
    try:
        with Image.open(io.BytesIO(contents)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")


async def save_upload(
    file: UploadFile,
    folder: str = "general",
    *,
    allowed_types=None,
    max_size: Optional[int] = None,
    validate_image: bool = True,
) -> str:
    allowed_types = allowed_types or IMAGE_ALLOWED_TYPES
    folder = _normalize_folder(folder)

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type",
        )

    contents = await file.read()
    size_limit = max_size or settings.MAX_FILE_SIZE
    if len(contents) > size_limit:
        max_mb = size_limit // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File too large. Max {max_mb}MB allowed")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    allowed_extensions = IMAGE_EXTENSIONS if validate_image else VIDEO_EXTENSIONS
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file extension")

    if validate_image:
        _validate_image(contents)

    filename = f"{uuid.uuid4().hex}.{ext}"

    save_dir = os.path.join(settings.UPLOAD_DIR, folder)
    os.makedirs(save_dir, exist_ok=True)

    async with aiofiles.open(os.path.join(save_dir, filename), "wb") as f:
        await f.write(contents)

    return f"/uploads/{folder}/{filename}"
