import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings


class StorageService:
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file: UploadFile, user_id: int) -> dict:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Dosya adı gerekli")

        ext = Path(file.filename).suffix.lower()
        safe_name = f"{user_id}_{uuid.uuid4().hex}{ext}"
        file_path = self.upload_dir / safe_name

        max_size = settings.MAX_UPLOAD_SIZE
        size = 0
        with file_path.open("wb") as buffer:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Dosya {max_size // (1024 * 1024)} MB sınırını aşıyor",
                    )
                buffer.write(chunk)

        return {
            "original_filename": file.filename,
            "storage_path": str(file_path.resolve()),
            "file_size": file_path.stat().st_size,
            "mime_type": file.content_type or "application/octet-stream",
        }

    def delete_file(self, storage_path: str) -> bool:
        try:
            Path(storage_path).unlink(missing_ok=True)
            return True
        except OSError:
            return False


storage_service = StorageService()
