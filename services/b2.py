"""Backblaze B2 storage with local-disk fallback when B2 is not configured."""
from __future__ import annotations

import logging
import os
import re
import uuid

from config import Config

logger = logging.getLogger("catatan.b2")

_api = None
_bucket = None
_init_tried = False


def b2_enabled() -> bool:
    return Config.B2_ENABLED


def _ensure_b2():
    global _api, _bucket, _init_tried
    if _init_tried:
        return _bucket
    _init_tried = True
    if not Config.B2_ENABLED:
        logger.info("B2 tidak dikonfigurasi — menggunakan penyimpanan lokal")
        return None
    try:
        from b2sdk.v2 import B2Api, InMemoryAccountInfo

        info = InMemoryAccountInfo()
        _api = B2Api(info)
        _api.authorize_account(
            "production",
            Config.B2_APPLICATION_KEY_ID,
            Config.B2_APPLICATION_KEY,
        )
        if Config.B2_BUCKET_ID:
            _bucket = _api.get_bucket_by_id(Config.B2_BUCKET_ID)
        else:
            _bucket = _api.get_bucket_by_name(Config.B2_BUCKET_NAME)
        logger.info("B2 terhubung: bucket=%s", Config.B2_BUCKET_NAME)
        return _bucket
    except Exception as e:
        logger.warning("Gagal inisialisasi B2 (%s) — fallback ke lokal", e)
        _bucket = None
        return None


def _safe_ext(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in Config.ALLOWED_IMAGE_EXT:
        raise ValueError("Ekstensi file tidak diizinkan")
    return ext


_IMG_FORMAT_BY_EXT = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
}
_MAX_IMAGE_PIXELS = 40_000_000  # 40 megapiksel


def _validate_image(file_bytes: bytes, ext: str) -> None:
    """Pastikan konten benar-benar gambar, format sesuai ekstensi, dan tidak terlalu besar."""
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(file_bytes)) as im:
            fmt = (im.format or "").lower()
            width, height = im.size
            im.verify()
    except Exception:
        raise ValueError("File bukan gambar yang valid") from None
    if fmt != _IMG_FORMAT_BY_EXT.get(ext):
        raise ValueError("Format gambar tidak sesuai dengan ekstensi file")
    if width * height > _MAX_IMAGE_PIXELS:
        raise ValueError("Resolusi gambar terlalu besar")


def upload_image(file_bytes: bytes, filename: str = "", folder: str = "catatan") -> dict:
    """Upload image to B2 (or local disk). Returns dict with url/path."""
    if not file_bytes:
        raise ValueError("File kosong")
    if len(file_bytes) > Config.MAX_UPLOAD_SIZE:
        raise ValueError(f"Ukuran file melebihi {Config.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")

    ext = _safe_ext(filename)
    _validate_image(file_bytes, ext)
    name = f"{uuid.uuid4().hex}{ext}"
    remote_path = f"{folder.strip('/')}/{name}"

    bucket = _ensure_b2()
    if bucket is not None:
        try:
            uploaded = bucket.upload_bytes(file_bytes, remote_path, content_type=_content_type(ext))
            file_id = getattr(uploaded, "file_id", None) or uploaded.as_dict().get("fileId")
            # Bucket privat: URL langsung B2 butuh auth header (tidak bisa dipakai <img>).
            # Proxy app menjadi URL utama; URL B2 hanya fallback bila proxy tidak relevan.
            url = f"/api/b2/file/{file_id}" if file_id else ""
            if not url and Config.B2_ENDPOINT:
                base = Config.B2_ENDPOINT.rstrip("/")
                if not base.startswith(("http://", "https://")):
                    base = f"https://{base}"
                url = f"{base}/{Config.B2_BUCKET_NAME}/{remote_path}"
            return {"url": url, "path": remote_path, "storage": "b2", "file_id": file_id}
        except Exception as e:
            logger.warning("Upload B2 gagal (%s) — fallback lokal", e)

    local_dir = os.path.join(Config.LOCAL_UPLOAD_DIR, folder.strip("/"))
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, name)
    with open(local_path, "wb") as f:
        f.write(file_bytes)
    rel_url = f"/static/uploads/{folder.strip('/')}/{name}"
    return {"url": rel_url, "path": rel_url, "storage": "local", "file_id": None}


def delete_file(storage: str, path: str = "", file_id: str | None = None) -> bool:
    """Delete a stored file. Prefer file_id for B2; path/url for local disk."""
    try:
        if file_id:
            if _delete_b2(file_id, path if storage == "b2" else ""):
                return True
            # path might be a B2 object name even if storage label is missing/wrong
            if path and not path.startswith("/") and _delete_b2(file_id, path):
                return True
        if path and path.startswith("/static/uploads/"):
            local = os.path.join(Config.BASE_DIR, path.lstrip("/"))
            real = os.path.realpath(local)
            root = os.path.realpath(Config.LOCAL_UPLOAD_DIR)
            if real.startswith(root + os.sep) and os.path.isfile(real):
                os.remove(real)
                return True
        if storage == "local" and path:
            # Guard against path traversal outside the uploads root
            root = os.path.realpath(Config.LOCAL_UPLOAD_DIR)
            candidates = []
            if path.startswith("/static/uploads/"):
                candidates.append(os.path.join(Config.BASE_DIR, path.lstrip("/")))
            elif os.path.isabs(path) or ".." in path or path.startswith("~"):
                candidates.append(path)
            else:
                candidates.append(os.path.join(root, path))
                candidates.append(os.path.join(Config.BASE_DIR, path.lstrip("/")))
            for cand in candidates:
                real = os.path.realpath(os.path.expanduser(cand))
                if not real.startswith(root + os.sep):
                    continue
                if os.path.isfile(real):
                    os.remove(real)
                    return True
    except Exception as e:
        logger.warning("Gagal hapus file: %s", e)
    return False


_B2_PROXY_RE = re.compile(r"^/api/b2/file/([A-Za-z0-9=_\-]+)")


def delete_media(
    storage: str | None = None,
    path: str = "",
    file_id: str | None = None,
    url: str = "",
) -> bool:
    """Delete by stored metadata and/or public URL (cover / markdown image)."""
    if not file_id and url:
        m = _B2_PROXY_RE.match(url.strip())
        if m:
            file_id = m.group(1)
            storage = storage or "b2"
    if not path and url.startswith("/static/uploads/"):
        path = url
        storage = storage or "local"
    if delete_file(storage or "", path=path or "", file_id=file_id):
        return True
    # URL-only local fallback
    if url.startswith("/static/uploads/"):
        return delete_file("local", path=url)
    return False


def _delete_b2(file_id: str, file_name: str = "") -> bool:
    bucket = _ensure_b2()
    if bucket is None or not file_id:
        return False
    name = (file_name or "").lstrip("/")
    if not name:
        try:
            info = bucket.get_file_info_by_id(file_id)
            name = getattr(info, "file_name", None) or ""
            if not name and isinstance(info, dict):
                name = info.get("fileName") or info.get("file_name") or ""
        except Exception as e:
            logger.warning("Gagal info file B2 file_id=%s: %s", file_id, e)
            return False
    if not name:
        logger.warning("Nama file B2 tidak diketahui untuk file_id=%s", file_id)
        return False
    bucket.delete_file_version(file_id, name)
    logger.info("Hapus B2: file_id=%s name=%s", file_id, name)
    return True


_B2_FILE_ID_RE = re.compile(r"/api/b2/file/([A-Za-z0-9=_\-]+)")
_LOCAL_UPLOAD_RE = re.compile(r"/static/uploads/[^\s\)\"\'<>]+")


def extract_media_refs(*texts: str) -> list[dict]:
    """Collect unique media refs from markdown/HTML/URLs."""
    seen: set[str] = set()
    refs: list[dict] = []
    for text in texts:
        if not text:
            continue
        for m in _B2_FILE_ID_RE.finditer(text):
            fid = m.group(1)
            key = f"b2:{fid}"
            if key not in seen:
                seen.add(key)
                refs.append({"storage": "b2", "file_id": fid, "path": "", "url": m.group(0)})
        for m in _LOCAL_UPLOAD_RE.finditer(text):
            u = m.group(0).rstrip(".,;:")
            key = f"local:{u}"
            if key not in seen:
                seen.add(key)
                refs.append({"storage": "local", "file_id": None, "path": u, "url": u})
    return refs


def download_by_file_id(file_id: str) -> tuple[bytes | None, str | None, str | None]:
    """Return (bytes, content_type, etag) for a B2 file id, or (None, None, None)."""
    bucket = _ensure_b2()
    if bucket is None or not file_id:
        return None, None, None
    try:
        import io

        download = bucket.download_file_by_id(file_id)
        buf = io.BytesIO()
        download.save(buf)
        data = buf.getvalue()
        content_type = None
        etag = None
        version = getattr(download, "download_version", None)
        if version is not None:
            content_type = getattr(version, "content_type", None)
            etag = getattr(version, "content_sha1", None)
        if not content_type:
            content_type = "application/octet-stream"
        return data, content_type, etag
    except Exception as e:
        logger.warning("Gagal unduh B2 file_id=%s: %s", file_id, e)
        return None, None, None


async def download_by_file_id_async(file_id: str) -> tuple[bytes | None, str | None, str | None]:
    import asyncio

    return await asyncio.to_thread(download_by_file_id, file_id)


async def upload_image_async(file_bytes: bytes, filename: str = "", folder: str = "catatan") -> dict:
    import asyncio

    return await asyncio.to_thread(upload_image, file_bytes, filename, folder)


async def delete_media_async(
    storage: str | None = None,
    path: str = "",
    file_id: str | None = None,
    url: str = "",
) -> bool:
    import asyncio

    return await asyncio.to_thread(
        delete_media, storage=storage, path=path, file_id=file_id, url=url
    )


def _content_type(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
