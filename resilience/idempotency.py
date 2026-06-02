"""
幂等性保证
防止重复请求导致重复执行
"""
import hashlib
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
from config.logger import get_logger
logger = get_logger(__name__)

# ==========================================
# 简易幂等性存储（生产环境用 Redis）
# ==========================================
class IdempotencyStore:
    """幂等性存储"""

    def __init__(self, ttl_minutes: int = 60):
        self._store: Dict[str, dict] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def _make_key(self, skill_id: str, user_id: int, params: dict) -> str:
        """生成幂等性 Key"""
        data = json.dumps({"skill_id": skill_id, "user_id": user_id, "params": params}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def check_and_set(self, key: str) -> bool:
        """
        检查是否已存在，不存在则设置
        返回 True 表示是新请求（可以执行）
        返回 False 表示重复请求（应跳过）
        """
        now = datetime.utcnow()

        # 清理过期记录
        expired = [k for k, v in self._store.items() if now - v["timestamp"] > self._ttl]
        for k in expired:
            del self._store[k]

        if key in self._store:
            logger.info("idempotent_skip", key=key)
            return False

        self._store[key] = {"timestamp": now, "status": "processing"}
        return True

    def mark_completed(self, key: str, result: dict):
        """标记请求已完成"""
        if key in self._store:
            self._store[key]["status"] = "completed"
            self._store[key]["result"] = result

    def get_result(self, key: str) -> Optional[dict]:
        """获取之前的结果"""
        record = self._store.get(key)
        if record and record["status"] == "completed":
            return record["result"]
        return None


# 全局单例
idempotency_store = IdempotencyStore()


# ==========================================
# 幂等性装饰器
# ==========================================
def idempotent(skill_id: str):
    """
    幂等性装饰器
    相同请求在 TTL 内只会执行一次
    """

    def decorator(func):
        async def wrapper(user_id: int, params: dict, **kwargs):
            key = idempotency_store._make_key(skill_id, user_id, params)

            # 检查是否已执行过
            cached_result = idempotency_store.get_result(key)
            if cached_result:
                logger.info("returning_cached_result", skill_id=skill_id, key=key)
                return cached_result

            # 检查是否正在处理
            if not idempotency_store.check_and_set(key):
                return {
                    "meta": {"status": "error", "error_code": "DUPLICATE_REQUEST"},
                    "data": None,
                    "display": "请勿重复提交相同请求",
                    "hints": ["请等待上一个请求完成"]
                }

            # 执行
            try:
                result = await func(user_id=user_id, params=params, **kwargs)
                idempotency_store.mark_completed(key, result)
                return result
            except Exception as e:
                # 失败时清除，允许重试
                del idempotency_store._store[key]
                raise e

        return wrapper

    return decorator