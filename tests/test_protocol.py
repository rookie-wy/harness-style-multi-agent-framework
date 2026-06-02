"""
MCP 协议格式校验
验证所有 Skill 返回是否遵守 MCPResponse 基类
"""
import pytest
from pydantic import ValidationError
from src.protocol.mcp_base import MCPMeta, MCPResponse


# ==========================================
# MCPMeta 字段校验
# ==========================================
class TestMCPMeta:
    def test_valid_meta(self):
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="success")
        assert meta.protocol_version == "2024-11-05"
        assert meta.skill_id == "test"
        assert meta.status == "success"
        assert meta.error_code is None

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            MCPMeta(skill_id="test", skill_version="1.0.0", status="invalid_status")

    def test_invalid_protocol_version(self):
        with pytest.raises(ValidationError):
            MCPMeta(skill_id="test", skill_version="1.0.0", status="success", protocol_version="wrong")

    def test_error_code_only_for_error_status(self):
        # error_code 在 status=error 时应该有值
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="error", error_code="TIMEOUT")
        assert meta.error_code == "TIMEOUT"

    def test_default_execution_time(self):
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="success")
        assert meta.execution_time_ms == 0


# ==========================================
# MCPResponse 字段校验
# ==========================================
class TestMCPResponse:
    def test_valid_response(self):
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="success")
        response = MCPResponse(meta=meta, data={"key": "value"}, display="测试结果")
        assert response.display == "测试结果"
        assert response.data == {"key": "value"}
        assert response.hints == []

    def test_display_is_required(self):
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="success")
        with pytest.raises(ValidationError):
            MCPResponse(meta=meta, data={})

    def test_error_response(self):
        meta = MCPMeta(skill_id="test", skill_version="1.0.0", status="error", error_code="TIMEOUT")
        response = MCPResponse(meta=meta, data=None, display="执行超时", hints=["请重试"])
        assert response.data is None
        assert "重试" in response.hints[0]


# ==========================================
# 所有 Skill 输出必须通过此测试
# ==========================================
def validate_skill_output(output: dict, expected_skill_id: str):
    """通用 Skill 输出校验器"""
    # 1. 必须有 meta
    assert "meta" in output, f"缺少 meta 字段"
    meta = output["meta"]

    # 2. meta 必要字段
    assert meta.get("skill_id") == expected_skill_id, f"skill_id 不匹配"
    assert meta["status"] in ("success", "partial", "error"), f"无效的 status: {meta['status']}"
    assert "protocol_version" in meta, "缺少 protocol_version"
    assert "skill_version" in meta, "缺少 skill_version"

    # 3. 必须有 display
    assert "display" in output, "缺少 display 字段"
    assert len(output["display"]) > 0, "display 不能为空"

    # 4. error 状态时必须有 error_code
    if meta["status"] == "error":
        assert meta.get("error_code") is not None, "error 状态必须提供 error_code"

    # 5. hints 必须是列表
    assert "hints" in output, "缺少 hints 字段"
    assert isinstance(output["hints"], list), "hints 必须是列表"