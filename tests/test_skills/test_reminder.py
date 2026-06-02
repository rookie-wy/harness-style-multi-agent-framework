"""Reminder Skill 回归测试"""
import pytest
from tests.test_protocol import validate_skill_output


class TestReminder:

    @pytest.mark.asyncio
    async def test_set_reminder(self, reminder_client):
        """测试设置提醒"""
        resp = await reminder_client.post("/execute", json={
            "params": {"content": "喝水", "delay_minutes": 3},
            "user_input": "3分钟后提醒我喝水"
        })
        assert resp.status_code == 200
        result = resp.json()
        validate_skill_output(result, "reminder")
        assert result["meta"]["status"] == "success"
        assert "喝水" in result["display"]

    @pytest.mark.asyncio
    async def test_extract_from_input(self, reminder_client):
        """测试从用户输入中提取提醒信息"""
        resp = await reminder_client.post("/execute", json={
            "params": {},
            "user_input": "5分钟后提醒我打电话"
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result["meta"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_default_delay(self, reminder_client):
        """测试默认延迟时间"""
        resp = await reminder_client.post("/execute", json={
            "params": {"content": "测试"},
            "user_input": "提醒我测试"
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result["meta"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_mcp_format(self, reminder_client):
        """测试 MCP 格式"""
        resp = await reminder_client.post("/execute", json={
            "params": {"content": "测试", "delay_minutes": 1},
            "user_input": ""
        })
        result = resp.json()
        validate_skill_output(result, "reminder")