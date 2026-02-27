"""
Storage Service — Supabase Storage integration for file uploads.

Handles property photos, documents, inspection images, and other file uploads.
Falls back to mock/dry-run mode when Supabase Storage is not configured.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Supabase Storage buckets
BUCKETS = {
    "imoveis": "erp-imoveis",
    "documentos": "erp-documentos",
    "vistorias": "erp-vistorias",
    "perfil": "erp-perfil",
    "contratos": "erp-contratos",
    "geral": "erp-geral",
}

# Allowed MIME types per bucket
ALLOWED_TYPES = {
    "imoveis": ["image/jpeg", "image/png", "image/webp", "image/heic"],
    "documentos": ["application/pdf", "image/jpeg", "image/png", "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    "vistorias": ["image/jpeg", "image/png", "image/webp", "video/mp4"],
    "perfil": ["image/jpeg", "image/png", "image/webp"],
    "contratos": ["application/pdf"],
    "geral": ["image/jpeg", "image/png", "image/webp", "application/pdf"],
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class StorageService:
    """Service for file uploads to Supabase Storage."""

    def __init__(self, supabase_client, org_id: str):
        self.client = supabase_client
        self.org_id = org_id
        self._storage_available: Optional[bool] = None

    def _check_storage(self) -> bool:
        """Check if Supabase Storage is available."""
        if self._storage_available is not None:
            return self._storage_available
        try:
            self.client.storage.list_buckets()
            self._storage_available = True
        except Exception:
            logger.info("[STORAGE] Supabase Storage not available, using dry-run mode")
            self._storage_available = False
        return self._storage_available

    def _get_bucket(self, categoria: str) -> str:
        return BUCKETS.get(categoria, BUCKETS["geral"])

    def _generate_path(self, categoria: str, filename: str) -> str:
        """Generate a unique storage path: org_id/categoria/uuid_filename."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        unique_name = f"{uuid.uuid4().hex[:12]}.{ext}"
        return f"{self.org_id}/{categoria}/{unique_name}"

    def validate_file(self, filename: str, content_type: str, size: int,
                      categoria: str = "geral") -> Optional[str]:
        """
        Validate file before upload. Returns error message or None if valid.
        """
        allowed = ALLOWED_TYPES.get(categoria, ALLOWED_TYPES["geral"])
        if content_type not in allowed:
            return f"Tipo de arquivo não permitido: {content_type}. Permitidos: {', '.join(allowed)}"
        if size > MAX_FILE_SIZE:
            max_mb = MAX_FILE_SIZE // (1024 * 1024)
            return f"Arquivo muito grande ({size // (1024*1024)}MB). Máximo: {max_mb}MB"
        return None

    async def upload(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        categoria: str = "geral",
    ) -> Dict[str, Any]:
        """
        Upload a file to Supabase Storage.

        Returns dict with url, path, bucket, size, content_type.
        In dry-run mode, returns a mock URL.
        """
        bucket = self._get_bucket(categoria)
        path = self._generate_path(categoria, filename)

        if not self._check_storage():
            mock_url = f"https://storage.mock.noctus.app/{bucket}/{path}"
            logger.info(f"[STORAGE DRY-RUN] Upload: {filename} -> {mock_url}")
            return {
                "url": mock_url,
                "path": path,
                "bucket": bucket,
                "size": len(file_bytes),
                "content_type": content_type,
                "dry_run": True,
            }

        try:
            self.client.storage.from_(bucket).upload(
                path,
                file_bytes,
                file_options={"content-type": content_type},
            )
            public_url = self.client.storage.from_(bucket).get_public_url(path)
            logger.info(f"[STORAGE] Uploaded: {filename} -> {public_url}")
            return {
                "url": public_url,
                "path": path,
                "bucket": bucket,
                "size": len(file_bytes),
                "content_type": content_type,
                "dry_run": False,
            }
        except Exception as e:
            logger.error(f"[STORAGE] Upload failed: {e}")
            raise

    async def upload_multiple(
        self,
        files: List[Tuple[bytes, str, str]],
        categoria: str = "geral",
    ) -> List[Dict[str, Any]]:
        """
        Upload multiple files. Each tuple is (file_bytes, filename, content_type).
        Returns list of upload results.
        """
        results = []
        for file_bytes, filename, content_type in files:
            result = await self.upload(file_bytes, filename, content_type, categoria)
            results.append(result)
        return results

    async def delete(self, path: str, categoria: str = "geral") -> bool:
        """Delete a file from storage."""
        bucket = self._get_bucket(categoria)

        if not self._check_storage():
            logger.info(f"[STORAGE DRY-RUN] Delete: {path}")
            return True

        try:
            self.client.storage.from_(bucket).remove([path])
            logger.info(f"[STORAGE] Deleted: {path}")
            return True
        except Exception as e:
            logger.error(f"[STORAGE] Delete failed: {e}")
            return False

    def get_signed_url(self, path: str, categoria: str = "geral",
                       expires_in: int = 3600) -> Optional[str]:
        """Get a temporary signed URL for private files."""
        bucket = self._get_bucket(categoria)

        if not self._check_storage():
            return f"https://storage.mock.noctus.app/{bucket}/{path}?token=mock-signed"

        try:
            result = self.client.storage.from_(bucket).create_signed_url(path, expires_in)
            return result.get("signedURL")
        except Exception as e:
            logger.error(f"[STORAGE] Signed URL failed: {e}")
            return None
