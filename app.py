"""Catatan — aplikasi catatan markdown berbasis Fenrir + MongoDB + Backblaze B2."""
import logging
import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("catatan")

from fenrir import (
    BodyLimitMiddleware,
    CORSMiddleware,
    CSRFMiddleware,
    Fenrir,
    GZipMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)

from config import Config

if not Config.SECRET_KEY:
    raise RuntimeError("SECRET_KEY belum di-set di .env")

app = Fenrir(
    title=Config.SITE_NAME,
    version="1.0.0",
    dev_mode=Config.DEV_MODE,
    docs_enabled=Config.DEV_MODE,
)

app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["DEBUG"] = Config.DEV_MODE

# ── Middleware (last added = outermost) ────────────────────────────────
# Order outermost→innermost: SecureCookie → BodyLimit → RateLimit →
# SecurityHeaders → RequestID → CSRF → GZip → app. BodyLimit first so large
# bodies are rejected before CSRF/RateLimit read them; SecureCookie
# outermost so it sees final Set-Cookie dari session middleware.


def _rate_limit_client_key(scope: dict) -> str:
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return "unknown"


app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(CSRFMiddleware, secret_key=Config.SECRET_KEY, auto_generate=True)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    SecurityHeadersMiddleware,
    hsts_max_age=31536000 if not Config.DEV_MODE else None,
    frame_options="SAMEORIGIN",
    csp=(
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'"
    ),
)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=Config.RATE_LIMIT_MAX,
    window_seconds=Config.RATE_LIMIT_WINDOW,
    key_func=_rate_limit_client_key,
)
app.add_middleware(
    BodyLimitMiddleware, max_content_length=Config.MAX_UPLOAD_SIZE * 4, status_code=413
)

from middleware.secure_cookie import SecureCookieMiddleware

app.add_middleware(SecureCookieMiddleware)

# ── Static ─────────────────────────────────────────────────────────────
from fenrir.static import StaticFiles

_static_cache = "public, max-age=0, must-revalidate" if Config.DEV_MODE else "public, max-age=3600"
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(Config.BASE_DIR, "static"), cache_control=_static_cache),
)

# ── Routes ─────────────────────────────────────────────────────────────
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.public import public_bp

app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)


@app.get("/admin")
async def admin_root_alias():
    from fenrir import redirect

    return redirect("/admin/")


@app.middleware("request")
async def ensure_db_ready(req):
    from database import ensure_ready, is_db_unavailable

    try:
        await ensure_ready(reconnect_retries=2)
    except Exception as e:
        if is_db_unavailable(e):
            logger.warning("DB ready check gagal: %s", e)
            from fenrir import HTMLResponse

            from template_helpers import render_template

            html, _ = render_template(
                "error.html",
                status=503,
                error_code=503,
                error_message="Database sementara tidak terjangkau",
            )
            return HTMLResponse(html, status=503)
        raise
    return None


def _error_page(status: int, message: str):
    from fenrir import HTMLResponse

    from template_helpers import render_template

    html, _ = render_template("error.html", status=status, error_code=status, error_message=message)
    return HTMLResponse(html, status=status)


def _db_unavailable_response(exc: Exception):
    from database import is_db_unavailable, mark_db_stale

    if not is_db_unavailable(exc):
        return None
    mark_db_stale()
    logger.warning("DB tidak tersedia: %s: %s", type(exc).__name__, exc)
    return _error_page(503, "Database sementara tidak terjangkau")


@app.exception(404)
async def not_found(req, exc):
    return _error_page(404, "Halaman tidak ditemukan")


@app.exception(403)
async def forbidden(req, exc):
    return _error_page(403, "Akses ditolak")


@app.exception(500)
async def server_error(req, exc):
    db_resp = _db_unavailable_response(exc)
    if db_resp is not None:
        return db_resp
    logger.exception("Internal Server Error: %s", exc)
    return _error_page(500, "Terjadi kesalahan pada server")


@app.exception(503)
async def service_unavailable(req, exc):
    return _error_page(503, "Layanan sementara tidak tersedia")


# pymongo/motor transient failures → friendly 503 (not raw 500)
try:
    import pymongo.errors as _perr

    def _make_mongo_handler():
        async def _mongo_transient(req, exc):
            resp = _db_unavailable_response(exc)
            if resp is not None:
                return resp
            return _error_page(503, "Database sementara tidak terjangkau")

        return _mongo_transient

    for _exc_cls in (
        _perr.NetworkTimeout,
        _perr.AutoReconnect,
        _perr.ServerSelectionTimeoutError,
        _perr.ConnectionFailure,
        _perr.ConfigurationError,
    ):
        app.register_error_handler(_exc_cls, _make_mongo_handler())

    # Private/cancelled op from pymongo during disconnect
    _cancelled = getattr(_perr, "_OperationCancelled", None)
    if isinstance(_cancelled, type) and issubclass(_cancelled, Exception):
        app.register_error_handler(_cancelled, _make_mongo_handler())
except Exception:  # pragma: no cover
    pass


@app.listener("before_server_start")
async def on_startup(app_instance):
    from database import ensure_ready

    await ensure_ready()
    logger.info("%s siap — http://localhost:8000", Config.SITE_NAME)


@app.listener("after_server_stop")
async def on_shutdown(app_instance):
    from database import close_db

    await close_db()




if __name__ == "__main__":
    app.run(
        host="0.0.0.0" if Config.DEV_MODE else "127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        app_path="app:app",
    )
