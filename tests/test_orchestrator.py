"""中控编排集成测试"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.central_agent.orchestrator import LifeAssistantOrchestrator


@pytest.mark.asyncio
class TestOrchestrator:

    @pytest.fixture
    async def orchestrator(self):
        return LifeAssistantOrchestrator()

    async def test_route_then_direct_reply(self, orchestrator, mock_skill_registry_response):
        """测试：不需要 Skill 时直接回复"""
        with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.raise_for_status = lambda: None
            mock_get.return_value.json = lambda: mock_skill_registry_response

            result = await orchestrator.process("你好，今天天气真好", user_id=1)
            assert len(result) > 0
            # 闲聊应该触发直接回复，不走 Skill

    async def test_parallel_skill_execution(self, orchestrator, mock_skill_registry_response):
        """测试：多个 Skill 并行执行"""
        # Mock 注册中心
        with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.raise_for_status = lambda: None
            mock_get.return_value.json = lambda: mock_skill_registry_response

            # Mock 批量加载
            mock_batch = AsyncMock()
            mock_batch.return_value.raise_for_status = lambda: None
            mock_batch.return_value.json = lambda: [
                {"skill_id": "calculator", "server_url": "http://localhost:8011"},
                {"skill_id": "reminder", "server_url": "http://localhost:8012"}
            ]

            # Mock 执行
            async def mock_execute(*args, **kwargs):
                url = args[0] if args else kwargs.get("url", "")
                if "calculator" in url:
                    return MagicMock(json=lambda: {"display": "100 / 3 = 33.33"}, raise_for_status=lambda: None)
                elif "reminder" in url:
                    return MagicMock(json=lambda: {"display": "已设置提醒"}, raise_for_status=lambda: None)
                return MagicMock(json=lambda: {"display": ""}, raise_for_status=lambda: None)

            with patch.object(orchestrator.client, 'post', new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = mock_execute

                result = await orchestrator.process(
                    "提醒我5分钟后打电话，顺便算一下100除以3",
                    user_id=1
                )

                assert "33.33" in result or "提醒" in result

    async def test_error_handling(self, orchestrator):
        """测试：Skill 全部失败时不应该崩溃"""
        with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Service unavailable")

            result = await orchestrator.process("算一下 1+1", user_id=1)
            # 应该优雅降级，而不是抛异常
            assert len(result) > 0