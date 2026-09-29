import logging

from fenrir import Blueprint, redirect, request, session

from middleware.auth import get_current_user
from models.user import authenticate_user
from template_helpers import render_template

auth_bp = Blueprint("auth", url_prefix="")

logger = logging.getLogger("auth")

_login_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = 300


def _client_ip() -> str:
    # Trust only the socket peer — ignore spoofable X-Forwarded-For
    scope = getattr(request, "scope", None) or {}
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return "unknown"


def _rate_limited(ip: str) -> bool:
    import threading
    import time

    lock = getattr(_rate_limited, "_lock", None)
    if lock is None:
        lock = threading.Lock()
        _rate_limited._lock = lock  # type: ignore[attr-defined]
    now = time.time()
    with lock:
        # Drop stale keys periodically to avoid unbounded growth
        if len(_login_attempts) > 256:
            for key in list(_login_attempts):
                _login_attempts[key] = [
                    t for t in _login_attempts.get(key, []) if now - t < LOGIN_WINDOW
                ]
                if not _login_attempts[key]:
                    _login_attempts.pop(key, None)
        attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW]
        _login_attempts[ip] = attempts
        if not attempts:
            _login_attempts.pop(ip, None)
            return False
        return len(attempts) >= LOGIN_MAX_ATTEMPTS


def _record_failure(ip: str) -> None:
    import threading
    import time

    lock = getattr(_rate_limited, "_lock", None)
    if lock is None:
        lock = threading.Lock()
        _rate_limited._lock = lock  # type: ignore[attr-defined]
    with lock:
        _login_attempts.setdefault(ip, []).append(time.time())


def _reset(ip: str) -> None:
    _login_attempts.pop(ip, None)


@auth_bp.get("/login")
async def login_page():
    user = get_current_user()
    if user:
        return redirect("/admin/")
    html, status = render_template("login.html", status=200, error=None)
    from fenrir import HTMLResponse

    return HTMLResponse(html, status=status)


@auth_bp.post("/login")
async def login_submit():
    import secrets

    from fenrir import HTMLResponse

    ip = _client_ip()
    if _rate_limited(ip):
        logger.warning("Login diblokir (rate limit) — ip=%s", ip)
        html, status = render_template(
            "login.html",
            status=429,
            error="Terlalu banyak percobaan login. Coba lagi dalam beberapa menit.",
        )
        return HTMLResponse(html, status=status)

    body = request.body or b""
    form = {}
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    from urllib.parse import parse_qs, unquote_plus

    for pair in text.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            form[unquote_plus(k)] = unquote_plus(v)

    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    csrf_form = form.get("csrf_token") or ""
    csrf_cookie = request.cookies.get("csrf_token") or request.scope.get("_csrf_token", "")

    if not username or not password:
        html, status = render_template("login.html", status=422, error="Username dan password wajib diisi.")
        return HTMLResponse(html, status=status)

    if request.scope.get("_csrf_error"):
        html, status = render_template(
            "login.html", status=403, error="Token keamanan tidak valid. Silakan coba lagi."
        )
        return HTMLResponse(html, status=status)

    user = await authenticate_user(username, password)
    if not user:
        _record_failure(ip)
        logger.warning("Login gagal: user=%r ip=%s", username, ip)
        html, status = render_template("login.html", status=401, error="Username atau password salah.")
        return HTMLResponse(html, status=status)

    _reset(ip)
    from datetime import datetime, timezone

    session.clear()
    session["sid"] = secrets.token_hex(16)
    session["user"] = {
        "id": user["_id"],
        "username": user["username"],
        "role": user.get("role", "admin"),
        "name": user.get("name") or user["username"],
    }
    session["login_time"] = datetime.now(timezone.utc).isoformat()
    return redirect("/admin/")


@auth_bp.post("/logout")
async def logout():
    if request.scope.get("_csrf_error"):
        return redirect("/login")
    session.clear()
    return redirect("/login")
