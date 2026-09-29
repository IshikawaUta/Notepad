import re
from datetime import datetime, timezone

from bson import ObjectId

from database import get_db
from models import parse_object_id, serialize_doc, serialize_docs
from models.category import slugify


def render_markdown(text: str) -> str:
    import markdown as md

    from services.sanitize import sanitize_html

    html = md.markdown(
        text or "",
        extensions=[
            "extra",
            "fenced_code",
            "tables",
            "toc",
            "sane_lists",
            "codehilite",
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "noclasses": False, "cssclass": "codehilite"},
            "toc": {"permalink": False},
        },
    )
    # Strip hard-coded light pygments background so theme CSS wins
    html = html.replace(' style="background: #f8f8f8"', "").replace(' style="background:#f8f8f8"', "")
    html = sanitize_html(html)
    return re.sub(r"<img(?![^>]*\bloading=)", '<img loading="lazy" decoding="async"', html)


LIST_PROJECTION = {
    "title": 1,
    "slug": 1,
    "excerpt": 1,
    "category_id": 1,
    "tags": 1,
    "status": 1,
    "is_pinned": 1,
    "cover_url": 1,
    "cover_file": 1,
    "word_count": 1,
    "reading_minutes": 1,
    "views": 1,
    "created_at": 1,
    "updated_at": 1,
    "published_at": 1,
}

_STATUSES = ("draft", "published", "archived")


def reading_stats(content: str) -> tuple[int, int]:
    words = len(re.findall(r"\S+", content or ""))
    minutes = max(1, round(words / 200)) if words else 0
    return words, minutes


def _clean_cover_file(cover_file: dict | None, cover_url: str | None) -> dict | None:
    """Normalize cover storage metadata; infer from proxy URL when missing."""
    url = (cover_url or "").strip()
    if not url:
        return None
    meta = dict(cover_file or {})
    storage = (meta.get("storage") or "").strip()
    path = (meta.get("path") or "").strip()
    file_id = (meta.get("file_id") or "").strip() or None
    if not file_id:
        m = re.match(r"^/api/b2/file/([A-Za-z0-9=_\-]+)", url)
        if m:
            file_id = m.group(1)
            storage = storage or "b2"
    if url.startswith("/static/uploads/"):
        storage = storage or "local"
        if not path:
            path = url
    if not storage:
        if file_id:
            storage = "b2"
        elif url.startswith("/static/uploads/"):
            storage = "local"
        else:
            storage = ""
    out = {
        "storage": storage,
        "path": path,
        "file_id": file_id,
        "url": url,
    }
    if not any((out["storage"], out["path"], out["file_id"])):
        return None
    return out


async def unique_note_slug(base: str, exclude_id: str | None = None) -> str:
    db = get_db()
    slug = slugify(base)
    candidate = slug
    i = 2
    while True:
        q = {"slug": candidate}
        if exclude_id:
            oid = parse_object_id(exclude_id)
            if oid:
                q["_id"] = {"$ne": ObjectId(oid)}
        if not await db.notes.find_one(q):
            return candidate
        candidate = f"{slug}-{i}"
        i += 1


async def create_note(data: dict) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    content = data.get("content", "") or ""
    words, minutes = reading_stats(content)
    slug = await unique_note_slug(data.get("title", "catatan"))
    status = data.get("status", "draft")
    if status not in _STATUSES:
        status = "draft"
    doc = {
        "title": (data.get("title") or "").strip(),
        "slug": slug,
        "excerpt": (data.get("excerpt") or "").strip(),
        "content": content,
        "content_html": render_markdown(content),
        "category_id": data.get("category_id") or None,
        "tags": data.get("tags") or [],
        "status": status,
        "is_pinned": bool(data.get("is_pinned")),
        "cover_url": (data.get("cover_url") or "").strip(),
        "cover_file": _clean_cover_file(data.get("cover_file"), data.get("cover_url")),
        "word_count": words,
        "reading_minutes": minutes,
        "views": 0,
        "created_at": now,
        "updated_at": now,
        "published_at": now if status == "published" else None,
    }
    result = await db.notes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


async def update_note(note_id: str, data: dict) -> dict | None:
    oid = parse_object_id(note_id)
    if oid is None:
        raise ValueError("ID catatan tidak valid")
    db = get_db()
    existing = await db.notes.find_one({"_id": ObjectId(oid)})
    if not existing:
        return None

    now = datetime.now(timezone.utc)
    update: dict = {"updated_at": now}

    new_title = (data.get("title") or "").strip()
    if new_title and new_title != existing.get("title"):
        update["title"] = new_title
        update["slug"] = await unique_note_slug(new_title, exclude_id=note_id)
    if "excerpt" in data:
        update["excerpt"] = (data["excerpt"] or "").strip()
    if "content" in data:
        content = data["content"] or ""
        words, minutes = reading_stats(content)
        update["content"] = content
        update["content_html"] = render_markdown(content)
        update["word_count"] = words
        update["reading_minutes"] = minutes
    if "category_id" in data:
        update["category_id"] = data["category_id"] or None
    if "tags" in data:
        update["tags"] = data["tags"] or []
    if "cover_url" in data:
        update["cover_url"] = (data["cover_url"] or "").strip()
        if "cover_file" in data:
            update["cover_file"] = _clean_cover_file(data.get("cover_file"), update["cover_url"])
        elif not update["cover_url"]:
            update["cover_file"] = None
        elif not existing.get("cover_file"):
            update["cover_file"] = _clean_cover_file(None, update["cover_url"])
    elif "cover_file" in data:
        update["cover_file"] = _clean_cover_file(data.get("cover_file"), existing.get("cover_url"))
    if "is_pinned" in data:
        update["is_pinned"] = bool(data["is_pinned"])
    if "status" in data and data["status"] in ("draft", "published", "archived"):
        new_status = data["status"]
        update["status"] = new_status
        if new_status == "published" and not existing.get("published_at"):
            update["published_at"] = now

    await db.notes.update_one({"_id": ObjectId(oid)}, {"$set": update})
    return serialize_doc(await db.notes.find_one({"_id": ObjectId(oid)}))


async def delete_note(note_id: str) -> int:
    oid = parse_object_id(note_id)
    if oid is None:
        raise ValueError("ID catatan tidak valid")
    db = get_db()
    result = await db.notes.delete_one({"_id": ObjectId(oid)})
    await db.note_revisions.delete_many({"note_id": ObjectId(oid)})
    return result.deleted_count


async def get_note_by_slug(slug: str, include_draft: bool = False):
    db = get_db()
    q = {"slug": slug}
    if not include_draft:
        q["status"] = "published"
    doc = await db.notes.find_one(q)
    if not doc:
        return None
    # Defense-in-depth: re-sanitize legacy content_html (pre-nh3) on read
    from services.sanitize import sanitize_html

    raw_html = doc.get("content_html") or ""
    safe = sanitize_html(raw_html)
    if safe != raw_html:
        await db.notes.update_one({"_id": doc["_id"]}, {"$set": {"content_html": safe}})
        doc["content_html"] = safe
    return serialize_doc(doc)


async def get_note_by_id(note_id: str):
    oid = parse_object_id(note_id)
    if oid is None:
        return None
    db = get_db()
    return serialize_doc(await db.notes.find_one({"_id": ObjectId(oid)}))


async def increment_views(note_id: str):
    oid = parse_object_id(note_id)
    if oid is None:
        return
    db = get_db()
    await db.notes.update_one({"_id": ObjectId(oid)}, {"$inc": {"views": 1}})


def schedule_view_increment(note_id: str):
    """Fire-and-forget view bump so the page response is not blocked."""
    import asyncio

    task = asyncio.create_task(increment_views(note_id))
    task.add_done_callback(lambda t: t.exception())


LIST_FIELDS_DEFAULT = ("title", "slug", "excerpt", "category_id", "tags", "status", "is_pinned", "cover_url", "word_count", "reading_minutes", "views", "created_at", "updated_at", "published_at")


async def list_notes(
    page: int = 1,
    limit: int = 9,
    status: str | None = "published",
    category_id: str | None = None,
    category_slug: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    pinned_first: bool = True,
    include_content: bool = False,
):
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    if category_id:
        query["category_id"] = category_id
    if category_slug:
        cat = await db.categories.find_one({"slug": category_slug})
        if not cat:
            return [], 0
        cat_id = str(cat["_id"])
        query["category_id"] = {"$in": [cat_id, cat["_id"]]}
    if tag:
        query["tags"] = tag
    if q:
        text_query = {"$text": {"$search": q}}
        try:
            text_total = await db.notes.count_documents({**query, **text_query})
        except Exception:
            text_total = 0
        if text_total:
            query = {**query, **text_query}
        else:
            pat = re.compile(re.escape(q), re.IGNORECASE)
            query = {
                **query,
                "$or": [{"title": pat}, {"excerpt": pat}, {"content": pat}, {"tags": pat}],
            }

    total = await db.notes.count_documents(query)
    skip = max(0, (page - 1) * limit)
    sort = [("is_pinned", -1), ("published_at", -1)] if pinned_first else [("published_at", -1)]
    projection = None if include_content else LIST_PROJECTION
    cursor = db.notes.find(query, projection)
    docs = await cursor.sort(sort).skip(skip).limit(limit).to_list(length=limit)
    return serialize_docs(docs), total


async def list_note_summaries(limit: int = 500) -> list[dict]:
    """Lightweight list for sitemap/feed (no content bodies)."""
    db = get_db()
    docs = (
        await db.notes.find({"status": "published"}, {"slug": 1, "title": 1, "excerpt": 1, "updated_at": 1})
        .sort("published_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return serialize_docs(docs)


async def get_related_notes(note: dict, limit: int = 3):
    query = {"status": "published", "_id": {"$ne": parse_object_id(note["_id"])}}
    if note.get("category_id"):
        query["category_id"] = note["category_id"]
        db = get_db()
        docs = await db.notes.find(query).sort("published_at", -1).limit(limit).to_list(length=limit)
        if len(docs) < limit and note.get("tags"):
            extra_q = {
                "status": "published",
                "_id": {"$ne": parse_object_id(note["_id"])},
                "tags": {"$in": note["tags"]},
            }
            existing_ids = {d["_id"] for d in docs} | {parse_object_id(note["_id"])}
            extra = await db.notes.find(extra_q).sort("published_at", -1).limit(limit * 2).to_list(length=limit * 2)
            for d in extra:
                if d["_id"] not in existing_ids and len(docs) < limit:
                    docs.append(d)
        return serialize_docs(docs)
    query["tags"] = {"$in": note.get("tags") or []}
    db = get_db()
    docs = await db.notes.find(query).sort("published_at", -1).limit(limit).to_list(length=limit)
    if len(docs) < limit:
        extra = await db.notes.find(
            {"status": "published", "_id": {"$ne": parse_object_id(note["_id"])}}
        ).sort("published_at", -1).to_list(length=limit)
        seen = {d["_id"] for d in docs} | {parse_object_id(note["_id"])}
        for d in extra:
            if d["_id"] not in seen and len(docs) < limit:
                docs.append(d)
    return serialize_docs(docs)


async def get_other_notes(note: dict, exclude_ids=(), limit: int = 3):
    excluded = []
    seen = set()
    for value in [note.get("_id"), *(exclude_ids or ())]:
        oid = parse_object_id(value) if not isinstance(value, ObjectId) else value
        if oid is not None and str(oid) not in seen:
            seen.add(str(oid))
            excluded.append(oid)
    query = {"status": "published", "_id": {"$nin": excluded}}
    db = get_db()
    docs = await db.notes.find(query).sort("published_at", -1).limit(limit).to_list(length=limit)
    return serialize_docs(docs)


async def get_all_tags():
    db = get_db()
    tags = await db.notes.distinct("tags", {"status": "published"})
    return sorted([t for t in tags if t])


async def get_stats() -> dict:
    from database import get_db

    db = get_db()

    # One $facet on notes + one count on categories (was 5+ sequential queries)
    facet = await db.notes.aggregate(
        [
            {
                "$facet": {
                    "by_status": [
                        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
                    ],
                    "views": [
                        {"$group": {"_id": None, "total": {"$sum": "$views"}}},
                    ],
                    "top": [
                        {"$match": {"status": "published"}},
                        {"$sort": {"views": -1}},
                        {"$limit": 5},
                    ],
                    "recent": [
                        {"$sort": {"updated_at": -1}},
                        {"$limit": 5},
                    ],
                }
            }
        ]
    ).to_list(length=1)
    row = facet[0] if facet else {}
    by_status = {r["_id"]: r["n"] for r in row.get("by_status") or []}
    views_rows = row.get("views") or []
    categories = await db.categories.count_documents({})
    return {
        "total": sum(by_status.values()),
        "published": by_status.get("published", 0),
        "draft": by_status.get("draft", 0),
        "archived": by_status.get("archived", 0),
        "categories": categories,
        "views": views_rows[0]["total"] if views_rows else 0,
        "top": serialize_docs(row.get("top") or []),
        "recent": serialize_docs(row.get("recent") or []),
    }


async def parse_tags(raw: str | list | None) -> list[str]:
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"[,;]", raw or "")
    seen = set()
    tags = []
    for item in items:
        t = str(item).strip().lower()
        if t and t not in seen and len(t) <= 40:
            seen.add(t)
            tags.append(t)
    return tags[:20]


async def get_tags_with_counts() -> list[dict]:
    db = get_db()
    cursor = db.notes.aggregate(
        [
            {"$match": {"status": "published"}},
            {"$unwind": "$tags"},
            {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
        ]
    )
    rows = await cursor.to_list(length=None)
    return [{"tag": r["_id"], "count": r["count"]} for r in rows]


REV_KEEP = 10
_REV_FIELDS = (
    "title",
    "excerpt",
    "content",
    "category_id",
    "tags",
    "status",
    "is_pinned",
    "cover_url",
)


async def add_revision(note_id: str, snapshot: dict | None = None) -> None:
    oid = parse_object_id(note_id)
    if oid is None:
        raise ValueError("ID catatan tidak valid")
    db = get_db()
    if snapshot is None:
        snapshot = await db.notes.find_one({"_id": ObjectId(oid)})
        if not snapshot:
            return
    doc = {"note_id": ObjectId(oid), "saved_at": datetime.now(timezone.utc)}
    for f in _REV_FIELDS:
        doc[f] = snapshot.get(f)
    doc["tags"] = snapshot.get("tags") or []
    doc["is_pinned"] = bool(snapshot.get("is_pinned"))
    doc["word_count"] = snapshot.get("word_count") or 0
    await db.note_revisions.insert_one(doc)
    excess = (
        await db.note_revisions.find({"note_id": ObjectId(oid)})
        .sort("saved_at", -1)
        .skip(REV_KEEP)
        .to_list(length=100)
    )
    if excess:
        await db.note_revisions.delete_many({"_id": {"$in": [r["_id"] for r in excess]}})


async def get_revisions(note_id: str) -> list[dict]:
    oid = parse_object_id(note_id)
    if oid is None:
        return []
    db = get_db()
    docs = (
        await db.note_revisions.find({"note_id": ObjectId(oid)})
        .sort("saved_at", -1)
        .to_list(length=REV_KEEP)
    )
    return serialize_docs(docs)
