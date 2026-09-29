import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    SECRET_KEY = os.getenv("SECRET_KEY", "")
    DEV_MODE = _bool("DEV_MODE", "0")
    PRODUCTION = not DEV_MODE

    MONGODB_URI = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "catatan")

    SITE_NAME = os.getenv("SITE_NAME", "Catatan")
    SITE_TAGLINE = os.getenv("SITE_TAGLINE", "Tulis, simpan, dan bagikan catatan markdown")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrator")

    B2_APPLICATION_KEY_ID = os.getenv("B2_APPLICATION_KEY_ID", "")
    B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
    B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "")
    B2_BUCKET_ID = os.getenv("B2_BUCKET_ID", "")
    B2_ENDPOINT = os.getenv("B2_ENDPOINT", "")
    B2_ENABLED = bool(B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY and B2_BUCKET_NAME)

    LOCAL_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
    MAX_UPLOAD_SIZE = _int("MAX_UPLOAD_SIZE", 5 * 1024 * 1024)
    ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

    RATE_LIMIT_MAX = _int("RATE_LIMIT_MAX", 200)
    RATE_LIMIT_WINDOW = _int("RATE_LIMIT_WINDOW", 60)

    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", "0" if DEV_MODE else "1")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_MAX_AGE = 60 * 60 * 24 * 7

    NOTES_PER_PAGE = _int("NOTES_PER_PAGE", 9)
    ADMIN_NOTES_PER_PAGE = _int("ADMIN_NOTES_PER_PAGE", 15)
