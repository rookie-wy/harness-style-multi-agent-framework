"""
熔断器 - Redis 持久化版本
状态机：CLOSED → OPEN → HALF_OPEN → CLOSED
"""
import time
from typing import Dict, Any
from ..infrastructure.redis_client import get_redis


class CircuitBreakerOpenError(Exception):
    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        super().__init__(f"熔断器已打开: {skill_id}")


class CircuitBreakerRegistry:
    """熔断器注册中心 - 所有状态存储在 Redis Hash"""

    async def register(self, skill_id: str, failure_threshold: int = 5, recovery_timeout: int = 30):
        """初始化熔断器配置（仅当 key 不存在时设置）"""
        r = await get_redis()
        key = f"cb:{skill_id}"
        if not await r.exists(key):
            await r.hset(key, mapping={
                "state": "CLOSED",
                "failure_count": 0,
                "failure_threshold": failure_threshold,
                "recovery_timeout": recovery_timeout,
                "opened_at": 0
            })

    async def record_failure(self, skill_id: str):
        """记录失败，自动触发熔断"""
        r = await get_redis()
        key = f"cb:{skill_id}"
        new_count = await r.hincrby(key, "failure_count", 1)
        threshold = int(await r.hget(key, "failure_threshold") or 5)
        if new_count >= threshold:
            await r.hset(key, "state", "OPEN")
            await r.hset(key, "opened_at", int(time.time()))

    async def record_success(self, skill_id: str):
        """调用成功，重置熔断器"""
        r = await get_redis()
        key = f"cb:{skill_id}"
        await r.hset(key, mapping={
            "state": "CLOSED",
            "failure_count": 0,
            "opened_at": 0
        })

    async def is_open(self, skill_id: str) -> bool:
        """检查熔断器是否打开（拒绝请求）"""
        r = await get_redis()
        key = f"cb:{skill_id}"
        state = await r.hget(key, "state")
        if state == "OPEN":
            opened_at = float(await r.hget(key, "opened_at") or 0)
            recovery_timeout = int(await r.hget(key, "recovery_timeout") or 30)
            if time.time() - opened_at >= recovery_timeout:
                # 进入半开状态，允许一次试探
                await r.hset(key, "state", "HALF_OPEN")
                return False
            return True
        return False

    async def get_status(self, skill_id: str = None) -> Dict[str, Any]:
        """查看熔断器状态"""
        r = await get_redis()
        if skill_id:
            key = f"cb:{skill_id}"
            status = await r.hgetall(key)
            if status:
                status["failure_count"] = int(status.get("failure_count", 0))
            return status if status else {"state": "UNKNOWN"}
        else:
            keys = await r.keys("cb:*")
            result = {}
            for key in keys:
                sid = key[3:]  # 去掉 "cb:" 前缀
                status = await r.hgetall(key)
                if status:
                    result[sid] = {
                        "state": status.get("state"),
                        "failure_count": int(status.get("failure_count", 0))
                    }
            return result


# 全局单例
breaker_registry = CircuitBreakerRegistry()


def with_circuit_breaker(skill_id: str, failure_threshold: int = 5, recovery_timeout: int = 30):
    """熔断装饰器（异步版本）"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 确保熔断器已注册
            await breaker_registry.register(skill_id, failure_threshold, recovery_timeout)
            # 检查熔断器
            if await breaker_registry.is_open(skill_id):
                raise CircuitBreakerOpenError(skill_id)
            try:
                result = await func(*args, **kwargs)
                await breaker_registry.record_success(skill_id)
                return result
            except Exception:
                await breaker_registry.record_failure(skill_id)
                raise
        return wrapper
    return decorator