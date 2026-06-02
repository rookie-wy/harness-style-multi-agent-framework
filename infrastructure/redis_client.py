"""
Redis 客户端 - 统一连接管理与常用操作封装
支持异步（asyncio）和同步两种模式
"""
import json
import redis.asyncio as aioredis
import redis
from typing import Optional, Any, List, Dict
from config.settings import REDIS_URL, REDIS_MAX_CONNECTIONS

# ==========================================
# 异步连接池（用于 FastAPI / LangGraph）
# ==========================================
async_pool = aioredis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=REDIS_MAX_CONNECTIONS,
    decode_responses=True,
)

# ==========================================
# 同步连接池（用于 Streamlit 同步代码）
# ==========================================
sync_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=REDIS_MAX_CONNECTIONS,
    decode_responses=True,
)

# ==========================================
# 获取连接
# ==========================================
async def get_redis() -> aioredis.Redis:
    """获取异步 Redis 连接"""
    return aioredis.Redis(connection_pool=async_pool)


def get_sync_redis() -> redis.Redis:
    """获取同步 Redis 连接"""
    return redis.Redis(connection_pool=sync_pool)


# ==========================================
# 通用缓存操作（自动 JSON 序列化）
# ==========================================
async def cache_get(key: str) -> Optional[Any]:
    """从缓存读取，自动 JSON 反序列化"""
    r = await get_redis()
    data = await r.get(key)
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data


async def cache_set(key: str, value: Any, ttl: int = None):
    """写入缓存，自动 JSON 序列化"""
    r = await get_redis()
    data = json.dumps(value, ensure_ascii=False)
    if ttl:
        await r.setex(key, ttl, data)
    else:
        await r.set(key, data)


async def cache_delete(key: str):
    """删除缓存"""
    r = await get_redis()
    await r.delete(key)


# ==========================================
# List 操作（对话历史）
# ==========================================
async def list_push(key: str, value: Any):
    """从右侧推入列表"""
    r = await get_redis()
    data = json.dumps(value, ensure_ascii=False)
    await r.rpush(key, data)


async def list_range(key: str, start: int, end: int) -> List[Any]:
    """获取列表范围，自动 JSON 反序列化"""
    r = await get_redis()
    items = await r.lrange(key, start, end)
    result = []
    for item in items:
        try:
            result.append(json.loads(item))
        except json.JSONDecodeError:
            result.append(item)
    return result


async def list_trim(key: str, start: int, end: int):
    """裁剪列表，保留指定范围"""
    r = await get_redis()
    await r.ltrim(key, start, end)


async def list_length(key: str) -> int:
    """获取列表长度"""
    r = await get_redis()
    return await r.llen(key)


# ==========================================
# Hash 操作（会话状态、熔断器）
# ==========================================
async def hash_set(key: str, field: str, value: Any):
    """设置 Hash 字段"""
    r = await get_redis()
    await r.hset(key, field, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)


async def hash_get(key: str, field: str) -> Optional[str]:
    """获取 Hash 字段"""
    r = await get_redis()
    return await r.hget(key, field)


async def hash_get_all(key: str) -> Dict[str, str]:
    """获取 Hash 所有字段"""
    r = await get_redis()
    return await r.hgetall(key)


async def hash_increment(key: str, field: str, amount: int = 1) -> int:
    """Hash 字段自增"""
    r = await get_redis()
    return await r.hincrby(key, field, amount)


async def hash_delete(key: str, *fields: str):
    """删除 Hash 字段"""
    r = await get_redis()
    if fields:
        await r.hdel(key, *fields)


# ==========================================
# Sorted Set 操作（限流）
# ==========================================
async def sorted_set_add(key: str, score: float, member: str):
    """添加 Sorted Set 成员"""
    r = await get_redis()
    await r.zadd(key, {member: score})


async def sorted_set_count(key: str, min_score: float, max_score: float) -> int:
    """统计分数范围内的成员数"""
    r = await get_redis()
    return await r.zcount(key, min_score, max_score)


async def sorted_set_remove_range(key: str, min_score: float, max_score: float):
    """移除分数范围内的成员"""
    r = await get_redis()
    await r.zremrangebyscore(key, min_score, max_score)


# ==========================================
# 通用操作
# ==========================================
async def set_expire(key: str, ttl: int):
    """设置过期时间"""
    r = await get_redis()
    await r.expire(key, ttl)


async def key_exists(key: str) -> bool:
    """检查 key 是否存在"""
    r = await get_redis()
    return await r.exists(key) > 0


async def health_check() -> bool:
    """Redis 健康检查"""
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception:
        return False