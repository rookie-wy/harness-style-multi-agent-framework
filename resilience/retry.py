"""
重试策略 - 基于 tenacity
"""
import functools
from typing import Type, Tuple, Optional, Callable
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import httpx
from config.logger import get_logger
logger = get_logger(__name__)
# ==========================================
# 可重试的错误类型
# ==========================================
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    httpx.HTTPStatusError,  # 只重试 5xx，具体在 filter 中判断
)


def is_retryable_http_error(exception: Exception) -> bool:
    """判断 HTTP 错误是否可重试"""
    if isinstance(exception, httpx.HTTPStatusError):
        # 只重试服务端错误和限流
        return exception.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exception, RETRYABLE_EXCEPTIONS)


# ==========================================
# 标准重试装饰器
# ==========================================
def skill_retry(
        max_attempts: int = 3,
        min_wait: int = 1,
        max_wait: int = 10
):
    """
    Skill 调用标准重试配置

    - 最多重试 3 次
    - 指数退避: 1s → 2s → 4s → ...
    - 只重试网络错误和 5xx
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, "WARNING"),
        after=after_log(logger, "DEBUG"),
        reraise=True
    )


# ==========================================
# 不同场景的重试策略
# ==========================================
class RetryPolicy:
    """预设重试策略"""

    @staticmethod
    def fast() -> callable:
        """快速重试：适合幂等操作"""
        return skill_retry(max_attempts=2, min_wait=0.5, max_wait=2)

    @staticmethod
    def standard() -> callable:
        """标准重试：适合大多数 Skill"""
        return skill_retry(max_attempts=3, min_wait=1, max_wait=10)

    @staticmethod
    def slow() -> callable:
        """慢重试：适合依赖外部 API 的 Skill"""
        return skill_retry(max_attempts=5, min_wait=2, max_wait=30)

    @staticmethod
    def none() -> callable:
        """不重试：适合非幂等操作"""
        return lambda func: func  # 直接返回原函数