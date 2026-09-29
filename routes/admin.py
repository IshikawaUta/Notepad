import math
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote_plus

import bcrypt
from fenrir import Blueprint, HTMLResponse, JSONResponse, Response, redirect, request

from config import Config
from middleware.auth import get_current_user, login_required, role_required
from models import parse_object_id
from models.category import (
    create_category,
    delete_category,
    get_all_categories,
    get_category_by_id,
    update_category,
)
from models.note import (
    add_revision,
    create_note,
    delete_note,
    get_note_by_id,
    get_revisions,
    get_stats,
    list_notes,
    parse_tags,
    update_note,
)
from models.user import authenticate_user, update_password, update_profile
from services import b2 as b2_service
from template_helpers import format_date, render_template

admin_bp = Blueprint("admin", url_prefix="/admin")


def _form() -> dict:
    body = request.body or b""
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        import json

        try:
            return json.loads(text or "{}")
        except Exception:
            return {}
    form = {}
    for pair in text.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            form[unquote_plus(k)] = unquote_plus(v)
    return form


def _page(default: int = 1) -> int:
    try:
        return max(1, int(request.args.get("page", str(default))))
    except ValueError:
        return default


def _ok(html: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status=status)


# ── Dashboard ──────────────────────────────────────────────────────────


@admin_bp.get("")
@admin_bp.get("/")
async def dashboard():
    user = get_current_user()
    if not user:
        return redirect("/login")
    from database import db_retry

    stats = await db_retry(get_stats)
    categories = await get_all_categories()
    html, status = render_template(
        "admin/dashboard.html",
        status=200,
        stats=stats,
        categories=categories,
        format_date=format_date,
    )
    return _ok(html, status)


def _cover_meta(form: dict) -> dict:
    return {
        "storage": (form.get("cover_storage") or "").strip(),
        "path": (form.get("cover_path") or "").strip(),
        "file_id": (form.get("cover_file_id") or "").strip() or None,
    }


def _ref_key(ref: dict) -> str:
    if ref.get("file_id"):
        return f"b2:{ref['file_id']}"
    return f"url:{ref.get('url') or ref.get('path') or ''}"


def _cover_ref(cover_url: str, cover_file: dict | None) -> dict | None:
    cf = cover_file or {}
    if not cover_url and not cf:
        return None
    extracted = b2_service.extract_media_refs(cover_url)
    if extracted:
        r = dict(extracted[0])
    else:
        r = {
            "storage": cf.get("storage"),
            "path": cf.get("path") or "",
            "file_id": cf.get("file_id"),
            "url": cover_url,
        }
    if cf.get("file_id"):
        r["file_id"] = cf["file_id"]
    if cf.get("path"):
        r["path"] = cf["path"]
    if cf.get("storage"):
        r["storage"] = cf["storage"]
    return r


async def _media_shared_elsewhere(ref: dict, exclude_id: str) -> bool:
    """Skip deleting a file still referenced by another note."""
    from bson import ObjectId

    from database import get_db
    from models import parse_object_id

    oid = parse_object_id(exclude_id)
    needle = ref.get("url") or ref.get("path") or ""
    fid = ref.get("file_id")
    db = get_db()
    q: dict = {"_id": {"$ne": ObjectId(oid)}} if oid else {}
    or_clauses: list[dict] = []
    if needle:
        or_clauses.append({"cover_url": needle})
        or_clauses.append({"content": {"$regex": re.escape(needle)}})
    if fid:
        or_clauses.append({"cover_url": f"/api/b2/file/{fid}"})
        or_clauses.append({"content": {"$regex": re.escape(f"/api/b2/file/{fid}")}})
        or_clauses.append({"cover_file.file_id": fid})
    if not or_clauses:
        return False
    q["$or"] = or_clauses
    return await db.notes.find_one(q) is not None


async def _purge_media_refs(refs: list[dict], exclude_id: str, keep: set[str]) -> None:
    seen: set[str] = set()
    for ref in refs:
        key = _ref_key(ref)
        if key in ("b2:", "url:") or key in seen or key in keep:
            continue
        seen.add(key)
        if exclude_id and await _media_shared_elsewhere(ref, exclude_id):
            continue
        await b2_service.delete_media_async(
            storage=ref.get("storage"),
            path=ref.get("path") or "",
            file_id=ref.get("file_id"),
            url=ref.get("url") or "",
        )


async def cleanup_note_media(note: dict) -> None:
    """Delete cover + image files no longer referenced by any other note."""
    exclude_id = str(note.get("_id") or "")
    refs: list[dict] = []
    cover_ref = _cover_ref(note.get("cover_url") or "", note.get("cover_file") or {})
    if cover_ref:
        refs.append(cover_ref)
    for ref in b2_service.extract_media_refs(note.get("content") or "", note.get("content_html") or ""):
        refs.append(dict(ref))
    await _purge_media_refs(refs, exclude_id, keep=set())


async def cleanup_edit_media(
    old_note: dict,
    new_content: str,
    new_cover_url: str,
    new_cover_file: dict | None,
    exclude_id: str,
) -> None:
    """Delete files removed from content/cover on save, unless still needed."""
    old_refs: list[dict] = []
    cover_ref = _cover_ref(old_note.get("cover_url") or "", old_note.get("cover_file") or {})
    if cover_ref:
        old_refs.append(cover_ref)
    for ref in b2_service.extract_media_refs(old_note.get("content") or "", old_note.get("content_html") or ""):
        old_refs.append(dict(ref))
    if not old_refs:
        return

    keep: set[str] = set()
    for ref in b2_service.extract_media_refs(new_content or ""):
        keep.add(_ref_key(ref))
    for ref in b2_service.extract_media_refs(new_cover_url or ""):
        keep.add(_ref_key(ref))
    if new_cover_url:
        keep.add("url:" + new_cover_url)
    if new_cover_file and new_cover_file.get("file_id"):
        keep.add("b2:" + new_cover_file["file_id"])
    await _purge_media_refs(old_refs, exclude_id, keep)


# ── Notes CRUD ─────────────────────────────────────────────────────────


@admin_bp.get("/catatan")
async def notes_list():
    user = get_current_user()
    if not user:
        return redirect("/login")
    page = _page()
    status_filter = (request.args.get("status") or "").strip() or None
    q = (request.args.get("q") or "").strip()
    if status_filter not in ("draft", "published", "archived"):
        status_filter = None

    notes, total = await list_notes(
        page=page,
        limit=Config.ADMIN_NOTES_PER_PAGE,
        status=status_filter,
        q=q or None,
        pinned_first=True,
    )
    categories = await get_all_categories()
    cat_map = {c["_id"]: c for c in categories}
    for n in notes:
        n["category"] = cat_map.get(n.get("category_id") or "")

    pages = max(1, math.ceil(total / Config.ADMIN_NOTES_PER_PAGE))
    html, status = render_template(
        "admin/notes.html",
        status=200,
        notes=notes,
        categories=categories,
        total=total,
        page=page,
        pages=pages,
        q=q,
        status_filter=status_filter,
        format_date=format_date,
    )
    return _ok(html, status)


@admin_bp.get("/catatan/tambah")
async def note_add():
    user = get_current_user()
    if not user:
        return redirect("/login")
    categories = await get_all_categories()
    html, status = render_template(
        "admin/note_form.html",
        status=200,
        note=None,
        categories=categories,
        format_date=format_date,
    )
    return _ok(html, status)


@admin_bp.post("/catatan/tambah")
async def note_add_submit():
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/catatan/tambah")
    form = _form()
    title = (form.get("title") or "").strip()
    if not title:
        categories = await get_all_categories()
        html, status = render_template(
            "admin/note_form.html",
            status=422,
            note=None,
            categories=categories,
            error="Judul wajib diisi.",
            form_data=form,
            format_date=format_date,
        )
        return _ok(html, status)

    tags = await parse_tags(form.get("tags"))
    cover_url = (form.get("cover_url") or "").strip()
    note = await create_note(
        {
            "title": title,
            "excerpt": form.get("excerpt"),
            "content": form.get("content"),
            "category_id": (form.get("category_id") or "").strip() or None,
            "tags": tags,
            "status": _status_value(form.get("status")),
            "is_pinned": form.get("is_pinned") in ("1", "on", "true"),
            "cover_url": cover_url,
            "cover_file": _cover_meta(form) if cover_url else None,
        }
    )
    return redirect(f"/admin/catatan/{note['_id']}/edit?created=1")


@admin_bp.get("/catatan/<note_id>/edit")
async def note_edit(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    note = await get_note_by_id(note_id)
    if not note:
        return redirect("/admin/catatan")
    categories = await get_all_categories()
    html, status = render_template(
        "admin/note_form.html",
        status=200,
        note=note,
        categories=categories,
        tags_raw=", ".join(note.get("tags") or []),
        created=request.args.get("created") == "1",
        format_date=format_date,
    )
    return _ok(html, status)


@admin_bp.post("/catatan/<note_id>/edit")
async def note_edit_submit(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect(f"/admin/catatan/{note_id}/edit")
    form = _form()
    title = (form.get("title") or "").strip()
    note = await get_note_by_id(note_id)
    if not note:
        return redirect("/admin/catatan")
    if not title:
        categories = await get_all_categories()
        html, status = render_template(
            "admin/note_form.html",
            status=422,
            note=note,
            categories=categories,
            error="Judul wajib diisi.",
            form_data=form,
            format_date=format_date,
        )
        return _ok(html, status)

    tags = await parse_tags(form.get("tags"))
    cover_url = (form.get("cover_url") or "").strip()
    await add_revision(note_id, note)
    await update_note(
        note_id,
        {
            "title": title,
            "excerpt": form.get("excerpt"),
            "content": form.get("content"),
            "category_id": (form.get("category_id") or "").strip() or None,
            "tags": tags,
            "status": _status_value(form.get("status"), note.get("status") or "draft"),
            "is_pinned": form.get("is_pinned") in ("1", "on", "true"),
            "cover_url": cover_url,
            "cover_file": _cover_meta(form) if cover_url else None,
        },
    )
    updated = await get_note_by_id(note_id)
    if updated:
        await cleanup_edit_media(
            old_note=note,
            new_content=form.get("content") or "",
            new_cover_url=(updated.get("cover_url") or "").strip(),
            new_cover_file=updated.get("cover_file"),
            exclude_id=note_id,
        )
    return redirect(f"/admin/catatan/{note_id}/edit?saved=1")


@admin_bp.get("/catatan/<note_id>/revisi")
async def note_revisions(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    note = await get_note_by_id(note_id)
    if not note:
        return redirect("/admin/catatan")
    revisions = await get_revisions(note_id)
    html, status = render_template(
        "admin/revisions.html",
        status=200,
        note=note,
        revisions=revisions,
        format_date=format_date,
        restored=request.args.get("restored") == "1",
    )
    return _ok(html, status)


@admin_bp.post("/catatan/<note_id>/revisi/pulihkan")
async def note_revision_restore(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect(f"/admin/catatan/{note_id}/revisi")
    form = _form()
    rev_id = (form.get("rev_id") or "").strip()
    note = await get_note_by_id(note_id)
    revisions = await get_revisions(note_id)
    rev = next((r for r in revisions if str(r["_id"]) == rev_id), None)
    if not note or not rev:
        return redirect(f"/admin/catatan/{note_id}/revisi")
    await add_revision(note_id, note)
    await update_note(
        note_id,
        {
            "title": rev.get("title") or note.get("title"),
            "excerpt": rev.get("excerpt") or "",
            "content": rev.get("content") or "",
            "category_id": rev.get("category_id"),
            "tags": rev.get("tags") or [],
            "status": rev.get("status") or note.get("status") or "draft",
            "is_pinned": bool(rev.get("is_pinned")),
        },
    )
    return redirect(f"/admin/catatan/{note_id}/revisi?restored=1")


@admin_bp.post("/catatan/<note_id>/hapus")
async def note_delete(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/catatan")
    note = await get_note_by_id(note_id)
    if note:
        await cleanup_note_media(note)
    await delete_note(note_id)
    return redirect("/admin/catatan")


@admin_bp.get("/catatan/<note_id>/lihat")
async def note_preview(note_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    note = await get_note_by_id(note_id)
    if not note:
        return redirect("/admin/catatan")
    return redirect(f"/catatan/{note['slug']}")


# ── Categories CRUD ────────────────────────────────────────────────────


async def _category_note_counts() -> dict[str, int]:
    """Single aggregation instead of N+1 count_documents per category."""
    from database import get_db

    db = get_db()
    pipeline = [
        {"$match": {"category_id": {"$ne": None}}},
        {"$group": {"_id": "$category_id", "count": {"$sum": 1}}},
    ]
    rows = await db.notes.aggregate(pipeline).to_list(length=500)
    counts: dict[str, int] = {}
    for r in rows:
        key = r.get("_id")
        if key is None:
            continue
        counts[str(key)] = counts.get(str(key), 0) + int(r.get("count") or 0)
    return counts


_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_color(value: str | None, default: str = "#6366f1") -> str:
    c = (value or "").strip()
    if _COLOR_RE.fullmatch(c):
        return c.lower()
    return default


def _status_value(value: str | None, default: str = "draft") -> str:
    v = (value or "").strip()
    if v in ("draft", "published", "archived"):
        return v
    return default


@admin_bp.get("/kategori")
async def categories_page():
    user = get_current_user()
    if not user:
        return redirect("/login")
    categories = await get_all_categories()
    db_notes = await _category_note_counts()
    html, status = render_template(
        "admin/categories.html",
        status=200,
        categories=categories,
        counts=db_notes,
        format_date=format_date,
    )
    return _ok(html, status)


@admin_bp.post("/kategori/tambah")
async def category_add():
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/kategori")
    form = _form()
    name = (form.get("name") or "").strip()
    if name:
        await create_category(
            name=name,
            description=form.get("description") or "",
            color=_safe_color(form.get("color")),
        )
    return redirect("/admin/kategori")


@admin_bp.post("/kategori/<category_id>/edit")
async def category_edit(category_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/kategori")
    form = _form()
    await update_category(
        category_id,
        {
            "name": form.get("name") or "",
            "description": form.get("description") or "",
            "color": _safe_color(form.get("color")),
        },
    )
    return redirect("/admin/kategori")


@admin_bp.post("/kategori/<category_id>/hapus")
async def category_delete(category_id: str):
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/kategori")
    cat = await get_category_by_id(category_id)
    if cat and await _category_has_notes(category_id):
        return redirect("/admin/kategori?error=terpakai")
    await delete_category(category_id)
    return redirect("/admin/kategori")


async def _category_has_notes(category_id: str) -> int:
    from bson import ObjectId

    from database import get_db
    from models import parse_object_id

    oid = parse_object_id(category_id)
    db = get_db()
    q = {"category_id": category_id}
    if oid:
        q = {"category_id": {"$in": [category_id, ObjectId(oid)]}}
    return await db.notes.count_documents(q)


# ── Upload (B2 / local) ────────────────────────────────────────────────


@admin_bp.post("/media/hapus")
async def media_delete():
    user = get_current_user()
    if not user:
        return JSONResponse({"error": "unauthorized"}, status=401)
    if request.scope.get("_csrf_error"):
        return JSONResponse({"error": "csrf"}, status=403)
    form = _form()
    url = (form.get("url") or "").strip()
    note_id = (form.get("note_id") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "url kosong"}, status=400)
    refs = b2_service.extract_media_refs(url)
    if not refs:
        return JSONResponse({"ok": False, "error": "url tidak dikenal"}, status=400)
    ref = refs[0]
    if url.rstrip("/") not in (ref.get("url") or "", ref.get("path") or ""):
        return JSONResponse({"ok": False, "error": "url tidak dikenal"}, status=400)
    if await _media_shared_elsewhere(ref, note_id):
        return JSONResponse({"ok": False, "error": "masih dipakai catatan lain"})
    ok = await b2_service.delete_media_async(
        storage=ref.get("storage"),
        path=ref.get("path") or "",
        file_id=ref.get("file_id"),
        url=ref.get("url") or "",
    )
    return JSONResponse({"ok": bool(ok), "error": "" if ok else "gagal menghapus"})


@admin_bp.post("/upload")
async def upload_file():
    user = get_current_user()
    if not user:
        return JSONResponse({"error": "unauthorized"}, status=401)
    if request.scope.get("_csrf_error"):
        return JSONResponse({"error": "csrf"}, status=403)

    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in content_type:
        return JSONResponse({"error": "multipart/form-data required"}, status=400)

    filename, file_bytes = await _parse_multipart_file()
    if not filename or not file_bytes:
        return JSONResponse({"error": "file not found"}, status=400)
    try:
        result = await b2_service.upload_image_async(file_bytes, filename, folder="catatan")
        # Never leak absolute filesystem paths or raw exception details
        public = {
            "ok": True,
            "url": result.get("url") or "",
            "storage": result.get("storage") or "",
            "file_id": result.get("file_id"),
            "path": result.get("path") if str(result.get("path") or "").startswith("/static/uploads/") else "",
        }
        return JSONResponse(public)
    except ValueError:
        return JSONResponse({"error": "File tidak valid atau terlalu besar"}, status=422)
    except Exception:
        return JSONResponse({"error": "Upload gagal"}, status=500)


async def _parse_multipart_file() -> tuple[str, bytes]:
    body = request.body or b""
    if not body:
        return "", b""
    ct = request.headers.get("content-type") or ""
    boundary = None
    for part in ct.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
    if not boundary:
        return "", b""
    delim = b"--" + boundary.encode()
    sections = body.split(delim)
    for section in sections:
        if b"Content-Disposition" not in section:
            continue
        if b'name="file"' not in section:
            continue
        header_blob, _, data = section.partition(b"\r\n\r\n")
        if not data:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        filename = ""
        for line in header_blob.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition"):
                for seg in line.decode("latin-1", errors="replace").split(";"):
                    seg = seg.strip()
                    if seg.startswith("filename="):
                        filename = seg.split("=", 1)[1].strip().strip('"')
        return filename, data
    return "", b""


# ── Profile & password ─────────────────────────────────────────────────


@admin_bp.get("/profil")
async def profile_page():
    user = get_current_user()
    if not user:
        return redirect("/login")
    html, status = render_template("admin/profile.html", status=200, ok=request.args.get("ok"), error=request.args.get("error"))
    return _ok(html, status)


@admin_bp.post("/profil")
async def profile_submit():
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/profil?error=csrf")
    form = _form()
    name = (form.get("name") or "").strip()
    username = (form.get("username") or "").strip()
    if not name or not username:
        return redirect("/admin/profil?error=invalid")
    await update_profile(user["id"], {"name": name, "username": username})
    session_user = dict(user)
    session_user["name"] = name
    session_user["username"] = username
    from fenrir import session

    session["user"] = session_user
    return redirect("/admin/profil?ok=1")


@admin_bp.post("/password")
async def password_submit():
    user = get_current_user()
    if not user:
        return redirect("/login")
    if request.scope.get("_csrf_error"):
        return redirect("/admin/profil?error=csrf")
    form = _form()
    current = form.get("current_password") or ""
    new = form.get("new_password") or ""
    confirm = form.get("confirm_password") or ""
    if len(new) < 8:
        return redirect("/admin/profil?error=short")
    if new != confirm:
        return redirect("/admin/profil?error=mismatch")
    auth = await authenticate_user(user["username"], current)
    if not auth:
        return redirect("/admin/profil?error=wrongpass")
    hashed = await _hash_password_async(new)
    await update_password(user["id"], hashed)
    from middleware.auth import revoke_user_sessions

    revoke_user_sessions(user["id"])
    # Keep current session valid by refreshing login_time after revoke
    from datetime import datetime, timezone

    from fenrir import session as _session

    _session["login_time"] = datetime.now(timezone.utc).isoformat()
    return redirect("/admin/profil?ok=password")


async def _hash_password_async(password: str) -> str:
    import asyncio

    return await asyncio.to_thread(
        lambda: bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    )


# ── API notifikasi (untuk badge dashboard) ─────────────────────────────


@admin_bp.get("/api/summary")
async def api_summary():
    user = get_current_user()
    if not user:
        return JSONResponse({"error": "unauthorized"}, status=401)
    stats = await get_stats()
    return JSONResponse(
        {
            "draft": stats["draft"],
            "published": stats["published"],
            "total": stats["total"],
            "categories": stats["categories"],
        }
    )
