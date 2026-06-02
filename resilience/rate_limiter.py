"""
限流器 - 基于 Redis Sorted Set 的滑动窗口算法（异步 + 同步）
"""
import sys
import os
import time

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from infrastructure.redis_client import get_redis, get_sync_redis


# 异步版本（供 FastAPI / LangGraph 内部使用）
async def check_rate_limit(user_id: int, max_requests: int = 10, window_sec: int = 60) -> bool:
    r = await get_redis()
    return await _check_rate_limit(r, user_id, max_requests, window_sec)


# 同步版本（供 Streamlit 使用）
def check_rate_limit_sync(user_id: int, max_requests: int = 10, window_sec: int = 60) -> bool:
    r = get_sync_redis()
    return _check_rate_limit_sync(r, user_id, max_requests, window_sec)


# 异步核心逻辑
async def _check_rate_limit(r, user_id: int, max_requests: int, window_sec: int) -> bool:
    key = f"rate_limit:{user_id}"
    now = int(time.time() * 1000)
    window_start = now - window_sec * 1000

    await r.zremrangebyscore(key, 0, window_start)
    count = await r.zcard(key)

    if count >= max_requests:
        return False

    member = f"{now}-{count + 1}"
    await r.zadd(key, {member: now})
    await r.expire(key, window_sec * 2)
    return True


# 同步核心逻辑
def _check_rate_limit_sync(r, user_id: int, max_requests: int, window_sec: int) -> bool:
    key = f"rate_limit:{user_id}"
    now = int(time.time() * 1000)
    window_start = now - window_sec * 1000

    r.zremrangebyscore(key, 0, window_start)
    count = r.zcard(key)

    if count >= max_requests:
        return False

    member = f"{now}-{count + 1}"
    r.zadd(key, {member: now})
    r.expire(key, window_sec * 2)
    return True