"""可靠性测试"""
import pytest
from unittest.mock import AsyncMock, patch
import httpx
from src.resilience.retry import skill_retry, is_retryable_http_error
from src.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitBreakerOpenError
from src.resilience.fallback import fallback_manager, call_with_fallback
from src.resilience.idempotency import idempotency_store


class TestRetry:
    async def test_retry_on_timeout(self):
        """超时应该重试"""
        call_count = 0

        @skill_retry(max_attempts=3, min_wait=0.1, max_wait=0.5)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 3

    async def test_no_retry_on_4xx(self):
        """4xx 错误不应该重试"""
        assert not is_retryable_http_error(
            httpx.HTTPStatusError("", request=None, response=MagicMock(status_code=400))
        )

    async def test_retry_on_5xx(self):
        """5xx 错误应该重试"""
        assert is_retryable_http_error(
            httpx.HTTPStatusError("", request=None, response=MagicMock(status_code=503))
        )


class TestCircuitBreaker:
    def test_breaker_opens_after_failures(self):
        """连续失败应该打开熔断器"""
        registry = CircuitBreakerRegistry()
        registry.register("test_skill", failure_threshold=3, recovery_timeout=30)

        registry.record_failure("test_skill")
        registry.record_failure("test_skill")
        assert not registry.is_open("test_skill")

        registry.record_failure("test_skill")
        assert registry.is_open("test_skill")

    def test_breaker_resets_on_success(self):
        """成功后应该关闭熔断器"""
        registry = CircuitBreakerRegistry()
        registry.register("test_skill", failure_threshold=3)

        registry.record_failure("test_skill")
        registry.record_failure("test_skill")
        registry.record_success("test_skill")

        assert not registry.is_open("test_skill")


class TestFallback:
    async def test_fallback_on_primary_failure(self):
        """主调用失败时返回降级响应"""

        async def always_fail():
            raise Exception("主服务异常")

        result = await call_with_fallback("calculator", always_fail)
        assert "暂时不可用" in result["display"]

    async def test_primary_success_no_fallback(self):
        """主调用成功时不触发降级"""

        async def success():
            return {"display": "计算完成"}

        result = await call_with_fallback("calculator", success)
        assert result["display"] == "计算完成"


class TestIdempotency:
    async def test_duplicate_request_skipped(self):
        """重复请求应该被跳过"""
        key = idempotency_store._make_key("calculator", 1, {"expression": "1+1"})

        first = idempotency_store.check_and_set(key)
        assert first == True

        second = idempotency_store.check_and_set(key)
        assert second == False