"""Samakan atribut `Secure` pada cookie dengan konteks request.

- HTTPS (langsung atau via X-Forwarded-Proto) & localhost: cookie diberi `Secure`.
- HTTP non-localhost (mis. akses via IP LAN tanpa HTTPS): `Secure` dilepas agar
  login tetap bisa dilakukan; di atas HTTP polos cookie memang tidak terlindungi
  transport apa pun, jadi atribut `Secure` hanya memblokir login tanpa manfaat.
"""
from __future__ import annotations

import re

_SECURE_RE = re.compile(r";\s*secure", re.IGNORECASE)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _wants_secure(scope: dict) -> bool:
    if scope.get("scheme") == "https":
        return True
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in (scope.get("headers") or [])
    }
    fwd = (headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if fwd == "https":
        return True
    host = (headers.get("host") or "").strip().lower()
    if host.startswith("["):
        host = host[1 : host.index("]")] if "]" in host else host[1:]
    else:
        host = host.split(":")[0]
    return host in _LOCAL_HOSTS


def _apply_secure(cookie: str, secure: bool) -> str:
    stripped = _SECURE_RE.sub("", cookie)
    return stripped + "; Secure" if secure else stripped


class SecureCookieMiddleware:
    """ASGI middleware: selaraskan atribut Secure cookie dengan konteks request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        secure = _wants_secure(scope)

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                headers = []
                for key, value in message.get("headers") or []:
                    if key.lower() == b"set-cookie":
                        value = _apply_secure(value.decode("latin-1"), secure).encode(
                            "latin-1"
                        )
                    headers.append((key, value))
                message = dict(message)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
