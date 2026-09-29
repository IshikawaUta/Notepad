import re
from datetime import datetime, timezone

from bson import ObjectId

from database import get_db
from models import parse_object_id, serialize_doc, serialize_docs


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "tanpa-judul"


async def unique_category_slug(base: str) -> str:
    db = get_db()
    slug = slugify(base)
    candidate = slug
    i = 2
    while await db.categories.find_one({"slug": candidate}):
        candidate = f"{slug}-{i}"
        i += 1
    return candidate


async def create_category(name: str, description: str = "", color: str = "#6366f1"):
    db = get_db()
    slug = await unique_category_slug(name)
    doc = {
        "name": name.strip(),
        "slug": slug,
        "description": (description or "").strip(),
        "color": color or "#6366f1",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.categories.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


async def get_all_categories():
    db = get_db()
    cursor = db.categories.find().sort("name", 1)
    docs = await cursor.to_list(length=1000)
    return serialize_docs(docs)


async def get_category_by_id(category_id: str):
    oid = parse_object_id(category_id)
    if oid is None:
        return None
    db = get_db()
    return serialize_doc(await db.categories.find_one({"_id": ObjectId(oid)}))


async def get_category_by_slug(slug: str):
    db = get_db()
    return serialize_doc(await db.categories.find_one({"slug": slug}))


async def update_category(category_id: str, data: dict):
    oid = parse_object_id(category_id)
    if oid is None:
        raise ValueError("ID kategori tidak valid")
    db = get_db()
    allowed = {}
    if "name" in data and data["name"].strip():
        allowed["name"] = data["name"].strip()
    if "description" in data:
        allowed["description"] = (data["description"] or "").strip()
    if "color" in data and data["color"]:
        allowed["color"] = data["color"]
    allowed["updated_at"] = datetime.now(timezone.utc)
    await db.categories.update_one({"_id": ObjectId(oid)}, {"$set": allowed})
    return await get_category_by_id(category_id)


async def delete_category(category_id: str) -> int:
    oid = parse_object_id(category_id)
    if oid is None:
        raise ValueError("ID kategori tidak valid")
    db = get_db()
    await db.notes.update_many(
        {"category_id": {"$in": [category_id, str(oid), ObjectId(oid)]}},
        {"$set": {"category_id": None, "updated_at": datetime.now(timezone.utc)}},
    )
    result = await db.categories.delete_one({"_id": ObjectId(oid)})
    return result.deleted_count


async def category_with_counts():
    db = get_db()
    pipeline = [
        {"$match": {"status": "published"}},
        {"$group": {"_id": "$category_id", "count": {"$sum": 1}}},
    ]
    rows = await db.notes.aggregate(pipeline).to_list(length=500)
    return {str(r["_id"]): r["count"] for r in rows if r.get("_id")}
