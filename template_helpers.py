from config import Config
from fenrir import session
from fenrir.context import request
from fenrir.templating import render_template as _fenrir_render


def get_csrf_token() -> str:
    return request.scope.get("_csrf_token", "")


def csrf_error() -> bool:
    return bool(request.scope.get("_csrf_error"))


def current_user():
    from middleware.auth import get_current_user

    return get_current_user()


def render_template(template_name: str, status: int = 200, **context):
    context.setdefault("site_name", Config.SITE_NAME)
    context.setdefault("site_tagline", Config.SITE_TAGLINE)
    context.setdefault("request", request)
    context.setdefault("csrf_token", get_csrf_token())
    context.setdefault("csrf_error", csrf_error())
    context.setdefault("user", current_user())
    context.setdefault("is_admin_area", template_name.startswith("admin/"))
    html = _fenrir_render(template_name, **context)
    return html, status


def excerpt_from(content: str, length: int = 160) -> str:
    import re

    text = re.sub(r"[#>*_`\[\]()!-]", " ", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


def request_base_url() -> str:
    try:
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            scheme = proto
        else:
            scheme = (request.scope.get("scheme") or "http").lower()
        if scheme not in ("http", "https"):
            scheme = "http"
        host = (request.headers.get("host") or "").strip()
        if host:
            return f"{scheme}://{host}"
    except Exception:
        pass
    return Config.BASE_URL


def format_date(value, fmt: str = "%d %b %Y") -> str:
    from datetime import datetime

    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    try:
        return value.strftime(fmt)
    except Exception:
        return str(value)
