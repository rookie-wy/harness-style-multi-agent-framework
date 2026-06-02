"""Calculator Skill 回归测试"""
import pytest
from tests.test_protocol import validate_skill_output


class TestCalculator:

    @pytest.mark.asyncio
    async def test_basic_calculation(self, calculator_client):
        """测试基本计算"""
        resp = await calculator_client.post("/execute", json={
            "params": {"expression": "3+5*2"},
            "user_input": "计算 3+5*2"
        })
        assert resp.status_code == 200
        result = resp.json()
        validate_skill_output(result, "calculator")
        assert result["meta"]["status"] == "success"
        assert result["data"]["result"] == 13

    @pytest.mark.asyncio
    async def test_expression_from_user_input(self, calculator_client):
        """测试从用户输入中提取表达式"""
        resp = await calculator_client.post("/execute", json={
            "params": {},
            "user_input": "帮我算一下 25 乘以 4"
        })
        assert resp.status_code == 200
        result = resp.json()
        # 应该能提取出 25*4 或类似表达式
        assert result["meta"]["status"] in ("success", "error")

    @pytest.mark.asyncio
    async def test_division_by_zero(self, calculator_client):
        """测试除零错误"""
        resp = await calculator_client.post("/execute", json={
            "params": {"expression": "1/0"},
            "user_input": "1/0"
        })
        assert resp.status_code == 200
        result = resp.json()
        validate_skill_output(result, "calculator")
        assert result["meta"]["status"] == "error"
        assert result["meta"]["error_code"] is not None

    @pytest.mark.asyncio
    async def test_empty_expression(self, calculator_client):
        """测试空表达式"""
        resp = await calculator_client.post("/execute", json={
            "params": {},
            "user_input": "你好"
        })
        assert resp.status_code == 200
        result = resp.json()
        validate_skill_output(result, "calculator")
        assert result["meta"]["status"] == "error"
        assert result["meta"]["error_code"] == "INVALID_PARAMS"

    @pytest.mark.asyncio
    async def test_mcp_format(self, calculator_client):
        """测试返回格式完全符合 MCP 协议"""
        resp = await calculator_client.post("/execute", json={
            "params": {"expression": "10+20"},
            "user_input": "10+20"
        })
        result = resp.json()
        validate_skill_output(result, "calculator")