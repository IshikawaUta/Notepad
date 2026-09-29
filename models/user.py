import bcrypt

from database import get_db
from models import serialize_doc

# Fixed dummy hash so missing-user logins take similar time as real checkpw.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalization-dummy", bcrypt.gensalt())


async def create_user(username: str, password_hashed: str, role: str, name: str = ""):
    from datetime import datetime, timezone

    db = get_db()
    user = {
        "username": username,
        "password_hashed": password_hashed,
        "role": role,
        "name": name,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(user)
    user["_id"] = result.inserted_id
    return serialize_doc(user)


async def find_user_by_username(username: str):
    db = get_db()
    return serialize_doc(await db.users.find_one({"username": username}))


async def authenticate_user(username: str, password: str):
    import asyncio

    user = await find_user_by_username(username)
    pw = password.encode("utf-8")
    if not user:
        await asyncio.to_thread(bcrypt.checkpw, pw, _DUMMY_HASH)
        return None
    try:
        stored = user["password_hashed"].encode("utf-8")
        ok = await asyncio.to_thread(bcrypt.checkpw, pw, stored)
        return user if ok else None
    except Exception:
        return None


async def update_password(user_id: str, password_hashed: str):
    from bson import ObjectId

    from models import parse_object_id

    oid = parse_object_id(user_id)
    if oid is None:
        raise ValueError("ID tidak valid")
    db = get_db()
    await db.users.update_one(
        {"_id": ObjectId(oid)},
        {"$set": {"password_hashed": password_hashed, "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}},
    )


async def update_profile(user_id: str, data: dict):
    from datetime import datetime, timezone

    from models import parse_object_id

    oid = parse_object_id(user_id)
    if oid is None:
        raise ValueError("ID tidak valid")
    from bson import ObjectId

    db = get_db()
    data = {k: v for k, v in data.items() if k in ("name", "username")}
    data["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one({"_id": ObjectId(oid)}, {"$set": data})
