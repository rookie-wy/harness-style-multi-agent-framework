"""
MCP 协议基类
定义所有 Skill 输出必须遵守的标准格式
"""
from pydantic import BaseModel, Field
from typing import TypeVar, Generic, Literal, Optional

TData = TypeVar("TData")

class MCPMeta(BaseModel):
    protocol_version: Literal["2024-11-05"] = "2024-11-05"
    skill_id: str
    skill_version: str
    status: Literal["success", "partial", "error"]
    error_code: Optional[str] = None
    execution_time_ms: int = 0

class MCPResponse(BaseModel, Generic[TData]):
    """所有 Skill 返回的标准格式"""
    meta: MCPMeta
    data: Optional[TData] = None
    display: str
    hints: list[str] = Field(default_factory=list)