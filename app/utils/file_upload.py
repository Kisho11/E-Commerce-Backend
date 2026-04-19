import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException
from app.config import settings

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


async def save_upload(file: UploadFile, folder: str = "general") -> str:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Allowed: JPEG, PNG, WebP, GIF",
        )

    contents = await file.read()
    if len(contents) > settings.MAX_FILE_SIZE:
        max_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File too large. Max {max_mb}MB allowed")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"

    save_dir = os.path.join(settings.UPLOAD_DIR, folder)
    os.makedirs(save_dir, exist_ok=True)

    async with aiofiles.open(os.path.join(save_dir, filename), "wb") as f:
        await f.write(contents)

    return f"/uploads/{folder}/{filename}"
