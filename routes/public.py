import json
import math

from fenrir import Blueprint, HTMLResponse, JSONResponse, Response, redirect, request

from config import Config
from models.category import category_with_counts, get_all_categories, get_category_by_slug
from models.note import (
    get_all_tags,
    get_note_by_slug,
    get_other_notes,
    get_tags_with_counts,
    list_notes,
    get_related_notes,
)
from template_helpers import format_date, render_template, request_base_url

public_bp = Blueprint("public", url_prefix="")


@public_bp.get("/favicon.ico")
async def favicon_ico():
    """Browsers request /favicon.ico by default — serve generated ICO."""
    from pathlib import Path

    from config import Config as C

    path = Path(C.BASE_DIR) / "favicon.ico"
    if not path.is_file():
        path = Path(C.BASE_DIR) / "static" / "favicon.ico"
    if not path.is_file():
        from fenrir.exceptions import HTTPException

        raise HTTPException(404)
    return Response(
        body=path.read_bytes(),
        content_type="image/x-icon",
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _page_arg(default: int = 1) -> int:
    try:
        return max(1, int(request.args.get("page", str(default))))
    except ValueError:
        return default


async def _render_index(page: int, q: str, category: str, tag: str):
    import asyncio

    from database import db_retry

    async def _load_all():
        return await asyncio.gather(
            list_notes(
                page=page,
                limit=Config.NOTES_PER_PAGE,
                status="published",
                category_slug=category or None,
                tag=tag or None,
                q=q or None,
            ),
            get_all_categories(),
            category_with_counts(),
            get_all_tags(),
        )

    (notes, total), categories, counts, tags = await db_retry(_load_all)

    pages = max(1, math.ceil(total / Config.NOTES_PER_PAGE))
    html, status = render_template(
        "index.html",
        status=200,
        notes=notes,
        categories=categories,
        category_counts=counts,
        tags=tags,
        total=total,
        page=page,
        pages=pages,
        q=q,
        active_category=category,
        active_tag=tag,
        format_date=format_date,
    )
    return HTMLResponse(html, status=status)


@public_bp.get("/")
async def index():
    return await _render_index(
        _page_arg(),
        (request.args.get("q") or "").strip(),
        (request.args.get("kategori") or "").strip(),
        (request.args.get("tag") or "").strip(),
    )


@public_bp.get("/tag")
async def tag_index():
    rows = await get_tags_with_counts()
    html, status = render_template("tag_index.html", status=200, tag_rows=rows)
    return HTMLResponse(html, status=status)


@public_bp.get("/tag/<slug>")
async def tag_page(slug: str):
    from urllib.parse import unquote

    return await _render_index(
        _page_arg(),
        (request.args.get("q") or "").strip(),
        "",
        unquote(slug or "").strip().lower(),
    )


@public_bp.get("/catatan/<slug>")
async def note_detail(slug: str):
    import asyncio

    note = await get_note_by_slug(slug, include_draft=False)
    if not note:
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="Catatan tidak ditemukan"
        )
        return HTMLResponse(html, status=status)

    from models.note import schedule_view_increment

    schedule_view_increment(note["_id"])
    note["views"] = int(note.get("views") or 0) + 1

    categories_task = get_all_categories()
    related_task = get_related_notes(note, limit=3)
    categories, related = await asyncio.gather(categories_task, related_task)
    other_notes = await get_other_notes(
        note, exclude_ids=[r.get("_id") for r in related], limit=3
    )
    cat_map = {c["_id"]: c for c in categories}
    category = cat_map.get(note.get("category_id") or "")

    base = request_base_url()
    note_url = f"{base}/catatan/{note['slug']}"
    cover = (note.get("cover_url") or "").strip()
    if cover and not cover.startswith(("http://", "https://")):
        cover = base + ("" if cover.startswith("/") else "/") + cover
    og_image = cover or f"{base}/og-image/{note['slug']}"

    def _iso(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v else ""

    published = note.get("published_at") or note.get("created_at")
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": note["title"],
        "url": note_url,
        "mainEntityOfPage": note_url,
        "description": note.get("excerpt") or "",
        "datePublished": _iso(published),
        "dateModified": _iso(note.get("updated_at") or published),
        "author": {"@type": "Person", "name": Config.SITE_NAME},
        "publisher": {"@type": "Organization", "name": Config.SITE_NAME},
    }
    if note.get("tags"):
        jsonld["keywords"] = ", ".join(note["tags"])
    if og_image:
        jsonld["image"] = og_image
    jsonld_json = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")

    html, status = render_template(
        "note.html",
        status=200,
        note=note,
        category=category,
        categories=categories,
        related=related,
        other_notes=other_notes,
        note_url=note_url,
        og_image=og_image,
        jsonld_json=jsonld_json,
        format_date=format_date,
    )
    return HTMLResponse(html, status=status)


@public_bp.get("/og-image/<slug>")
async def og_card(slug: str):
    import hashlib as _sha
    from pathlib import Path as _Path

    from services.og import generate_note_card

    note = await get_note_by_slug(slug, include_draft=False)
    if not note:
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="Catatan tidak ditemukan"
        )
        return HTMLResponse(html, status=status)

    cache_dir = _Path(Config.BASE_DIR) / "cache" / "og"
    key = _sha.sha1(
        f"{note['title']}|{note.get('updated_at')}|{note.get('excerpt') or ''}".encode("utf-8")
    ).hexdigest()[:16]
    fpath = cache_dir / f"{slug}-{key}.png"
    etag = f'"{key}"'
    if not fpath.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        accent = "#6366f1"
        cat_id = note.get("category_id")
        if cat_id:
            for c in await get_all_categories():
                if str(c["_id"]) == str(cat_id):
                    accent = c.get("color") or accent
                    break
        data = generate_note_card(note["title"], Config.SITE_NAME, accent)
        tmp = fpath.with_suffix(".tmp.png")
        tmp.write_bytes(data)
        tmp.replace(fpath)
    else:
        data = fpath.read_bytes()

    if (request.headers.get("if-none-match") or "").strip() == etag:
        return Response(
            body=b"", content_type="image/png", status=304,
            headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
        )
    return Response(
        body=data,
        content_type="image/png",
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )


@public_bp.get("/catatan/<slug>/unduh")
async def note_download(slug: str):
    from middleware.auth import get_current_user

    user = get_current_user()
    note = await get_note_by_slug(slug, include_draft=bool(user))
    if not note:
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="Catatan tidak ditemukan"
        )
        return HTMLResponse(html, status=status)
    body = (note.get("content") or "").encode("utf-8")
    return Response(
        body=body,
        content_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.md"',
            "Cache-Control": "private, max-age=0",
        },
    )


@public_bp.get("/kategori/<slug>")
async def category_page(slug: str):
    cat = await get_category_by_slug(slug)
    if not cat:
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="Kategori tidak ditemukan"
        )
        return HTMLResponse(html, status=status)
    return redirect(f"/?kategori={cat['slug']}")


@public_bp.get("/search")
async def search():
    from urllib.parse import urlencode

    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect("/")
    return redirect("/?" + urlencode({"q": q}))


@public_bp.get("/api/search")
async def api_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return JSONResponse([])
    notes, _ = await list_notes(page=1, limit=8, status="published", q=q)
    results = [
        {
            "title": n["title"],
            "slug": n["slug"],
            "excerpt": n.get("excerpt") or "",
            "url": f"/catatan/{n['slug']}",
        }
        for n in notes
    ]
    return JSONResponse(results)


@public_bp.get("/api/b2/file/<file_id>")
async def b2_file(file_id: str):
    import hashlib
    import re as _re

    from services import b2 as b2_service

    if not _re.fullmatch(r"[A-Za-z0-9=_\-]+", file_id or ""):
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="File tidak ditemukan"
        )
        return HTMLResponse(html, status=status)

    data, content_type, sha = await b2_service.download_by_file_id_async(file_id)
    if data is None:
        html, status = render_template(
            "error.html", status=404, error_code=404, error_message="File tidak ditemukan"
        )
        return HTMLResponse(html, status=status)

    etag = f'"{sha}"' if sha else '"' + hashlib.sha1(data).hexdigest() + '"'
    if_none_match = request.headers.get("if-none-match") or ""
    if etag in [p.strip() for p in if_none_match.split(",")]:
        return Response(
            body=b"",
            content_type=content_type or "application/octet-stream",
            status=304,
            headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
        )
    return Response(
        body=data,
        content_type=content_type or "application/octet-stream",
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )


@public_bp.get("/sitemap.xml")
async def sitemap():
    import asyncio
    from datetime import datetime, timezone

    from models.note import list_note_summaries

    notes_task = list_note_summaries(limit=1000)
    categories_task = get_all_categories()
    tags_task = get_tags_with_counts()
    notes, categories, tag_rows = await asyncio.gather(
        notes_task, categories_task, tags_task
    )

    from urllib.parse import quote as _quote

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = request_base_url()
    urls = [
        f"""  <url><loc>{base}/</loc><lastmod>{today}</lastmod><priority>1.0</priority></url>""",
        f"""  <url><loc>{base}/tag</loc><lastmod>{today}</lastmod><priority>0.5</priority></url>""",
    ]
    for n in notes:
        urls.append(
            f"""  <url><loc>{base}/catatan/{n['slug']}</loc><lastmod>{str(n.get('updated_at') or today)[:10]}</lastmod><priority>0.8</priority></url>"""
        )
    for c in categories:
        urls.append(
            f"""  <url><loc>{base}/?kategori={c['slug']}</loc><lastmod>{today}</lastmod><priority>0.6</priority></url>"""
        )
    for t in tag_rows:
        urls.append(
            f"""  <url><loc>{base}/tag/{_quote(t['tag'])}</loc><lastmod>{today}</lastmod><priority>0.6</priority></url>"""
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(
        body=body.encode("utf-8"),
        content_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@public_bp.get("/robots.txt")
async def robots():
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nSitemap: {request_base_url()}/sitemap.xml\n"
    return Response(body=body.encode("utf-8"), content_type="text/plain; charset=utf-8")


@public_bp.get("/feed.xml")
async def feed():
    from config import Config as C
    from models.note import list_note_summaries

    notes = await list_note_summaries(limit=20)

    base = request_base_url()
    items = []
    for n in notes:
        link = f"{base}/catatan/{n['slug']}"
        desc = (n.get("excerpt") or "")[:200]
        items.append(
            f"    <item><title>{_xml(n['title'])}</title><link>{link}</link>"
            f"<description>{_xml(desc)}</description></item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{_xml(C.SITE_NAME)}</title><link>{base}/</link>"
        f"<description>{_xml(C.SITE_TAGLINE)}</description>"
        + "\n".join(items)
        + "</channel></rss>"
    )
    return Response(
        body=body.encode("utf-8"),
        content_type="application/rss+xml",
        headers={"Cache-Control": "public, max-age=1800"},
    )


def _xml(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
