import io
import os
import uuid
import aiofiles
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile, HTTPException
from app.config import settings

IMAGE_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
SAFE_FOLDERS = {"general", "products", "categories"}
IMAGE_EXTENSIONS = {"jpeg", "jpg", "png", "webp", "gif"}


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
) -> str:
    folder = _normalize_folder(folder)

    if file.content_type not in IMAGE_ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type",
        )

    contents = await file.read()
    size_limit = settings.MAX_FILE_SIZE
    if len(contents) > size_limit:
        max_mb = size_limit // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File too large. Max {max_mb}MB allowed")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension")

    _validate_image(contents)

    filename = f"{uuid.uuid4().hex}.{ext}"

    save_dir = os.path.join(settings.UPLOAD_DIR, folder)
    os.makedirs(save_dir, exist_ok=True)

    async with aiofiles.open(os.path.join(save_dir, filename), "wb") as f:
        await f.write(contents)

    return f"/uploads/{folder}/{filename}"
