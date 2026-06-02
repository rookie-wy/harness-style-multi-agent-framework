"""MCP 标准错误码"""
from enum import Enum

class ErrorCode(str, Enum):
    INVALID_PARAMS = "INVALID_PARAMS"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    TIMEOUT = "TIMEOUT"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class SkillError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)