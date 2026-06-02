"""FastAPI 依赖注入：从请求中获取当前用户"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .security import verify_token

security_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> dict:
    """从 Bearer token 中解析当前用户信息"""
    return verify_token(credentials.credentials)