from functools import wraps

from fenrir import HTMLResponse, redirect, session

SESSION_MAX_AGE = 60 * 60 * 24 * 7

# user_id → ISO timestamp of last password change (process-local revocation)
_revoked_logins: dict[str, str] = {}


def revoke_user_sessions(user_id: str) -> None:
    from datetime import datetime, timezone

    _revoked_logins[str(user_id)] = datetime.now(timezone.utc).isoformat()


def _session_expired() -> bool:
    from datetime import datetime, timezone

    login_time = session.get("login_time")
    if not login_time:
        return True
    try:
        dt = datetime.fromisoformat(str(login_time))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() > SESSION_MAX_AGE
    except Exception:
        return True


def _session_revoked(user_id: str) -> bool:
    from datetime import datetime, timezone

    revoked_at = _revoked_logins.get(str(user_id))
    if not revoked_at:
        return False
    login_time = session.get("login_time")
    if not login_time:
        return True
    try:
        login_dt = datetime.fromisoformat(str(login_time))
        if login_dt.tzinfo is None:
            login_dt = login_dt.replace(tzinfo=timezone.utc)
        rev_dt = datetime.fromisoformat(revoked_at)
        if rev_dt.tzinfo is None:
            rev_dt = rev_dt.replace(tzinfo=timezone.utc)
        # Sessions logged in before the password change are invalid
        return login_dt < rev_dt
    except Exception:
        return True


def get_current_user() -> dict | None:
    try:
        user = session.get("user")
    except RuntimeError:
        return None
    if not user:
        return None
    if _session_expired() or _session_revoked(user.get("id") or ""):
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    async def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect("/login")
        return await view(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        async def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect("/login")
            if roles and user.get("role") not in roles:
                from template_helpers import render_template

                html, status = render_template("admin/403.html", status=403, user=user)
                return HTMLResponse(html, status=status)
            return await view(*args, **kwargs)

        return wrapper

    return decorator
