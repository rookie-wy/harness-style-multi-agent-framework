"""
对话记忆持久化存储（Redis 缓存 + SQLite 持久化）
采用写穿透模式：写 Redis 同步 + SQLite 异步持久化
读优先从 Redis 获取，未命中从 SQLite 加载并回写 Redis
"""
import aiosqlite
import os
import asyncio
import json
from src.infrastructure.redis_client import (
    list_push,
    list_range,
    list_trim,
    list_length,
    set_expire,
    cache_delete,
    key_exists,
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conversations.db")

# Redis 缓存键前缀和保留条数
CACHE_KEY_PREFIX = "chat:history:"
MAX_CACHE_SIZE = 50
CACHE_TTL = 7 * 86400  # 7 天


async def init_db():
    """初始化 SQLite 表（如果不存在）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_msg_user ON messages(user_id)")
        await db.commit()


async def save_message(user_id: int, role: str, content: str):
    """保存消息：写 Redis 缓存 + 异步写 SQLite"""
    await init_db()
    msg = {"role": role, "content": content}
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"

    # 写入 Redis List
    await list_push(cache_key, msg)
    # 裁剪为最近 MAX_CACHE_SIZE 条
    await list_trim(cache_key, -MAX_CACHE_SIZE, -1)
    # 刷新 TTL
    await set_expire(cache_key, CACHE_TTL)

    # 异步持久化到 SQLite
    asyncio.create_task(_save_to_db(user_id, role, content))


async def _save_to_db(user_id: int, role: str, content: str):
    """后台异步写入 SQLite"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content)
            )
            await db.commit()
    except Exception as e:
        # 记录日志但不影响主流程
        from config.logger import get_logger
        logger = get_logger(__name__)
        logger.error("save_message_to_db_failed", error=str(e))


async def load_messages(user_id: int, limit: int = 50) -> list:
    """加载消息：优先从 Redis 读取，未命中从 SQLite 加载并回写"""
    await init_db()
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"

    # 尝试从 Redis 读取
    exists = await key_exists(cache_key)
    if exists:
        messages = await list_range(cache_key, -limit, -1)
        if messages:
            return messages

    # 从 SQLite 加载
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit)
        )
        rows = await cursor.fetchall()

    messages = [{"role": row[0], "content": row[1]} for row in rows]

    # 回写 Redis
    if messages:
        for msg in messages:
            await list_push(cache_key, msg)
        await list_trim(cache_key, -MAX_CACHE_SIZE, -1)
        await set_expire(cache_key, CACHE_TTL)

    return messages


async def clear_messages(user_id: int):
    """清除消息：同时删除 Redis 缓存和 SQLite 记录"""
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"
    await cache_delete(cache_key)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_or_create_user() -> int:
    """获取或创建用户（保持原有逻辑不变）"""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        cursor = await db.execute("SELECT MAX(id) FROM users")
        row = await cursor.fetchone()
        if row[0] is None:
            await db.execute("INSERT INTO users DEFAULT VALUES")
            await db.commit()
            return 1
        return row[0]


async def get_all_users() -> list:
    """获取所有用户（保持原有逻辑不变）"""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, created_at FROM users ORDER BY id")
        rows = await cursor.fetchall()
        return [{"id": row[0], "created_at": row[1]} for row in rows]



# ==========================================
# 同步版本（供 Streamlit 等同步框架使用）
# ==========================================
import sqlite3
from src.infrastructure.redis_client import get_sync_redis

SYNC_DB_PATH = DB_PATH  # 复用同一个数据库文件


def save_message_sync(user_id: int, role: str, content: str):
    """同步保存消息：Redis 缓存 + SQLite 持久化"""
    msg = {"role": role, "content": content}
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"

    # 同步写 Redis
    r = get_sync_redis()
    r.rpush(cache_key, json.dumps(msg, ensure_ascii=False))
    r.ltrim(cache_key, -MAX_CACHE_SIZE, -1)
    r.expire(cache_key, CACHE_TTL)

    # 同步写 SQLite
    try:
        conn = sqlite3.connect(SYNC_DB_PATH)
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        from config.logger import get_logger
        logger = get_logger(__name__)
        logger.error("save_message_sync_db_failed", error=str(e))


def load_messages_sync(user_id: int, limit: int = 50) -> list:
    """同步加载消息：优先 Redis，未命中读 SQLite 并回写"""
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"

    # 尝试从 Redis 读取
    r = get_sync_redis()
    if r.exists(cache_key):
        items = r.lrange(cache_key, -limit, -1)
        if items:
            return [json.loads(m) for m in items]

    # 从 SQLite 加载
    conn = sqlite3.connect(SYNC_DB_PATH)
    cursor = conn.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()

    messages = [{"role": row[0], "content": row[1]} for row in rows]

    # 回写 Redis
    if messages:
        for msg in messages:
            r.rpush(cache_key, json.dumps(msg, ensure_ascii=False))
        r.ltrim(cache_key, -MAX_CACHE_SIZE, -1)
        r.expire(cache_key, CACHE_TTL)

    return messages


def clear_messages_sync(user_id: int):
    """同步清除消息"""
    cache_key = f"{CACHE_KEY_PREFIX}{user_id}"
    r = get_sync_redis()
    r.delete(cache_key)

    conn = sqlite3.connect(SYNC_DB_PATH)
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_or_create_user_sync() -> int:
    """同步获取或创建用户"""
    conn = sqlite3.connect(SYNC_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor = conn.execute("SELECT MAX(id) FROM users")
    row = cursor.fetchone()
    if row[0] is None:
        conn.execute("INSERT INTO users DEFAULT VALUES")
        conn.commit()
        user_id = 1
    else:
        user_id = row[0]
    conn.close()
    return user_id