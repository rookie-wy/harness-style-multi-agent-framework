"""
路由回归测试
测试中控智能体是否能正确匹配 Skill
"""
import pytest
import json
import os
from unittest.mock import AsyncMock, patch
from src.central_agent.orchestrator import LifeAssistantOrchestrator, AssistantState

# 加载测试用例
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
with open(os.path.join(FIXTURES_DIR, "routing_cases.json"), "r", encoding="utf-8") as f:
    ROUTING_CASES = json.load(f)


# ==========================================
# 正向测试：应该路由到正确的 Skill
# ==========================================
@pytest.mark.asyncio
@pytest.mark.parametrize("case", ROUTING_CASES["positive_cases"],
                         ids=[c["id"] for c in ROUTING_CASES["positive_cases"]])
async def test_positive_routing(case, mock_skill_registry_response):
    """测试正向路由：用户明确请求时，应匹配正确的 Skill"""
    orchestrator = LifeAssistantOrchestrator()

    # Mock 注册中心返回
    with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: mock_skill_registry_response

        state = {
            "user_input": case["user_input"],
            "user_id": 1,
            "session_id": "test",
            "available_skills": [],
            "routed_skills": [],
            "tool_definitions": [],
            "tool_results": [],
            "knowledge_context": "",
            "final_response": "",
            "error": None
        }

        result = await orchestrator.router_node(state)

        for expected in case["expected_skills"]:
            assert expected in result["routed_skills"], \
                f"[{case['id']}] 期望匹配 '{expected}'，但实际匹配: {result['routed_skills']}"

        for unexpected in case.get("unexpected_skills", []):
            assert unexpected not in result["routed_skills"], \
                f"[{case['id']}] 不应该匹配 '{unexpected}'"


# ==========================================
# 负向测试：不应该路由到错误 Skill
# ==========================================
@pytest.mark.asyncio
@pytest.mark.parametrize("case", ROUTING_CASES["negative_cases"],
                         ids=[c["id"] for c in ROUTING_CASES["negative_cases"]])
async def test_negative_routing(case, mock_skill_registry_response):
    """测试负向路由：不应该误匹配 Skill"""
    orchestrator = LifeAssistantOrchestrator()

    with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: mock_skill_registry_response

        state = {
            "user_input": case["user_input"],
            "user_id": 1, "session_id": "test",
            "available_skills": [], "routed_skills": [],
            "tool_definitions": [], "tool_results": [],
            "knowledge_context": "", "final_response": "", "error": None
        }

        result = await orchestrator.router_node(state)

        for unexpected in case.get("unexpected_skills", []):
            assert unexpected not in result["routed_skills"], \
                f"[{case['id']}] 不应该匹配 '{unexpected}'"


# ==========================================
# 边界测试
# ==========================================
@pytest.mark.asyncio
class TestEdgeCases:
    async def test_empty_input(self, mock_skill_registry_response):
        """空输入不应该路由任何 Skill"""
        orchestrator = LifeAssistantOrchestrator()

        with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.raise_for_status = lambda: None
            mock_get.return_value.json = lambda: mock_skill_registry_response

            state = {
                "user_input": "",
                "user_id": 1, "session_id": "test",
                "available_skills": [], "routed_skills": [],
                "tool_definitions": [], "tool_results": [],
                "knowledge_context": "", "final_response": "", "error": None
            }

            result = await orchestrator.router_node(state)
            assert result["routed_skills"] == []

    async def test_registry_unavailable(self):
        """注册中心不可用时，应该设置 error 而不是崩溃"""
        orchestrator = LifeAssistantOrchestrator()

        with patch.object(orchestrator.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            state = {
                "user_input": "算一下 1+1",
                "user_id": 1, "session_id": "test",
                "available_skills": [], "routed_skills": [],
                "tool_definitions": [], "tool_results": [],
                "knowledge_context": "", "final_response": "", "error": None
            }

            result = await orchestrator.router_node(state)
            assert result["error"] is not None
            assert "路由失败" in result["error"]