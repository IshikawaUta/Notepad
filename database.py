import asyncio
import logging
import threading
from typing import Awaitable, Callable, Optional, TypeVar

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import Config

logger = logging.getLogger("catatan.database")

_db_lock = threading.Lock()
_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_ready = False
_ready_lock = None

T = TypeVar("T")


def init_db() -> AsyncIOMotorDatabase:
    global _client, _db
    with _db_lock:
        if _db is not None:
            return _db
        if not Config.MONGODB_URI:
            raise RuntimeError("MONGODB_URI belum di-set di .env")
        _client = AsyncIOMotorClient(
            Config.MONGODB_URI,
            maxPoolSize=50,
            minPoolSize=1,
            maxIdleTimeMS=30000,
            connectTimeoutMS=10000,
            serverSelectionTimeoutMS=10000,
            socketTimeoutMS=60000,
            retryWrites=True,
            retryReads=True,
            appname="catatan",
        )
        _db = _client[Config.MONGODB_DB_NAME]
        logger.info("MongoDB terhubung: db=%s", Config.MONGODB_DB_NAME)
        return _db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        return init_db()
    return _db


def is_db_unavailable(exc: BaseException | None) -> bool:
    """True for transient network/DNS/pool failures worth treating as 503."""
    if exc is None:
        return False
    try:
        import pymongo.errors as perr

        if isinstance(
            exc,
            (
                perr.NetworkTimeout,
                perr.AutoReconnect,
                perr.ServerSelectionTimeoutError,
                perr.ConnectionFailure,
                perr.ConfigurationError,
            ),
        ):
            return True
    except Exception:
        pass
    name = type(exc).__name__
    if name in (
        "_OperationCancelled",
        "NetworkTimeout",
        "AutoReconnect",
        "ServerSelectionTimeoutError",
        "ConfigurationError",
        "ConnectionFailure",
        "CursorNotFound",
    ):
        return True
    msg = str(exc).lower()
    if any(
        s in msg
        for s in (
            "operation cancelled",
            "network timeout",
            "timed out",
            "no address associated with hostname",
            "resolution lifetime expired",
            "server selection timed out",
            "connection pool",
        )
    ):
        return True
    # Walk causes (pymongo often chains TimeoutError)
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        return is_db_unavailable(cause)
    return False


def mark_db_stale() -> None:
    """Force next ensure_ready() to reconnect after a failed operation."""
    global _ready
    _ready = False
    logger.warning("Database ditandai stale — akan reconnect di request berikutnya")


async def ensure_ready(force: bool = False, reconnect_retries: int = 5) -> None:
    """Idempotent startup: connect, index, seed admin (reconnect if marked stale)."""
    global _ready
    if _ready and not force:
        return

    global _ready_lock
    if _ready_lock is None:
        _ready_lock = asyncio.Lock()
    async with _ready_lock:
        if _ready and not force:
            return
        # Drop broken client before reconnect
        if force or _client is None:
            await close_db()
        try:
            init_db()
            await wait_for_db(retries=max(1, reconnect_retries))
            await create_indexes()
            await seed_admin()
            await reset_admin_password()
        except Exception as e:
            mark_db_stale()
            raise
        _ready = True
        logger.info("%s siap (db ready)", Config.SITE_NAME)


async def wait_for_db(retries: int = 5, delay: float = 1.0) -> None:
    client = _client
    if client is None:
        init_db()
        client = _client
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            assert client is not None
            await client.admin.command("ping")
            return
        except Exception as e:
            last_exc = e
            logger.warning("MongoDB ping gagal (%s/%s): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                await asyncio.sleep(delay * (attempt + 1))
    raise RuntimeError(f"MongoDB tidak terjangkau: {last_exc}")


async def close_db() -> None:
    global _client, _db, _ready
    with _db_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None
            _db = None
            _ready = False
            logger.info("MongoDB connection ditutup")


async def db_retry(fn: Callable[[], Awaitable[T]], attempts: int = 2) -> T:
    """Run an async DB operation; one reconnect+retry on transient network errors."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as e:
            last = e
            if not is_db_unavailable(e) or attempt >= attempts - 1:
                if is_db_unavailable(e):
                    mark_db_stale()
                raise
            logger.warning("DB transient error (retry %s/%s): %s", attempt + 1, attempts, e)
            mark_db_stale()
            try:
                await ensure_ready(force=True, reconnect_retries=2)
            except Exception as re:
                logger.warning("Reconnect gagal: %s", re)
                raise e from re
            await asyncio.sleep(0.2 * (attempt + 1))
    assert last is not None
    raise last


async def create_indexes() -> None:
    db = get_db()
    await db.users.create_index("username", unique=True)
    await db.categories.create_index("slug", unique=True)
    await db.notes.create_index("slug", unique=True)
    await db.notes.create_index([("status", 1), ("published_at", -1)])
    await db.notes.create_index([("status", 1), ("is_pinned", -1), ("published_at", -1)])
    await db.notes.create_index([("category_id", 1), ("status", 1)])
    await db.notes.create_index("tags")
    await db.note_revisions.create_index([("note_id", 1), ("saved_at", -1)])
    text_weights = {"title": 5, "tags": 3, "excerpt": 2, "content": 1}
    try:
        info = await db.notes.index_information()
        current = info.get("notes_text") or {}
        if current.get("weights") != text_weights:
            try:
                await db.notes.drop_index("notes_text")
            except Exception:
                pass
            await db.notes.create_index(
                [("title", "text"), ("excerpt", "text"), ("content", "text"), ("tags", "text")],
                name="notes_text",
                weights=text_weights,
                default_language="english",
            )
    except Exception:
        try:
            await db.notes.create_index(
                [("title", "text"), ("excerpt", "text"), ("content", "text"), ("tags", "text")],
                name="notes_text",
                weights=text_weights,
                default_language="english",
            )
        except Exception:
            pass
    # Drop legacy inefficient indexes if present
    for name in ("title_1_content_1", "content_1"):
        try:
            await db.notes.drop_index(name)
        except Exception:
            pass


async def seed_admin() -> None:
    import bcrypt

    from models.user import find_user_by_username

    existing = await find_user_by_username(Config.ADMIN_USERNAME)
    if existing:
        return
    if not Config.ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD wajib di-set saat create admin pertama")

    password_hashed = bcrypt.hashpw(
        Config.ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    from datetime import datetime, timezone

    from models.user import create_user

    await create_user(
        username=Config.ADMIN_USERNAME,
        password_hashed=password_hashed,
        role="admin",
        name=Config.ADMIN_NAME,
    )
    logger.warning(
        "Akun admin dibuat: username=%s",
        Config.ADMIN_USERNAME,
    )


async def reset_admin_password() -> None:
    """Sync admin password hash with ADMIN_PASSWORD from .env when provided."""
    import bcrypt

    if not Config.ADMIN_PASSWORD:
        return
    from models.user import find_user_by_username

    existing = await find_user_by_username(Config.ADMIN_PASSWORD and Config.ADMIN_USERNAME)
    if not existing:
        return
    desired = Config.ADMIN_PASSWORD.encode("utf-8")
    current = (existing.get("password_hashed") or "").encode("utf-8")
    try:
        if current and bcrypt.checkpw(desired, current):
            return
    except Exception:
        pass
    hashed = bcrypt.hashpw(desired, bcrypt.gensalt()).decode("utf-8")
    from datetime import datetime, timezone

    from bson import ObjectId

    from database import get_db as _gdb

    db = _gdb()
    await db.users.update_one(
        {"_id": ObjectId(existing["_id"])},
        {"$set": {"password_hashed": hashed, "updated_at": datetime.now(timezone.utc)}},
    )
    logger.warning("Password admin disinkronkan dari ADMIN_PASSWORD di .env")
