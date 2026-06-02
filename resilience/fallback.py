"""
降级策略
当 Skill 不可用时，返回预设的降级响应
"""
from typing import Dict, Callable, Optional, Any
from config.logger import get_logger
logger = get_logger(__name__)
# ==========================================
# 降级响应预设
# ==========================================
DEFAULT_FALLBACKS: Dict[str, Dict] = {
    "calculator": {
        "meta": {"status": "error", "error_code": "DEGRADED",
                 "skill_id": "calculator", "skill_version": "1.0.0"},
        "data": None,
        "display": "计算服务暂时不可用，请稍后重试",
        "hints": ["你可以稍后再试，或者手动计算"]
    },
    "reminder": {
        "meta": {"status": "error", "error_code": "DEGRADED",
                 "skill_id": "reminder", "skill_version": "1.0.0"},
        "data": None,
        "display": "提醒服务暂时不可用，请稍后重试",
        "hints": ["你可以自己设置手机闹钟"]
    },
    "weather": {
        "meta": {"status": "error", "error_code": "DEGRADED",
                 "skill_id": "weather", "skill_version": "1.0.0"},
        "data": None,
        "display": "天气服务暂时不可用，请查看手机天气App",
        "hints": ["可以直接问我今天是晴天还是雨天，我根据经验回答"]
    },
    "note": {
        "meta": {"status": "error", "error_code": "DEGRADED",
                 "skill_id": "note", "skill_version": "1.0.0"},
        "data": None,
        "display": "笔记服务暂时不可用，请稍后重试",
        "hints": ["你可以先用手机备忘录记录"]
    },
    # 默认降级响应
    "default": {
        "meta": {"status": "error", "error_code": "DEGRADED"},
        "data": None,
        "display": "服务暂时不可用，请稍后重试",
        "hints": []
    }
}


# ==========================================
# 降级管理器
# ==========================================
class FallbackManager:
    """降级策略管理器"""

    def __init__(self, fallbacks: Dict = None):
        self.fallbacks = fallbacks or DEFAULT_FALLBACKS

    def get_fallback(self, skill_id: str) -> Dict:
        """获取某个 Skill 的降级响应"""
        if skill_id in self.fallbacks:
            return self.fallbacks[skill_id]
        return self.fallbacks["default"].copy()

    def register_fallback(self, skill_id: str, fallback: Dict):
        """注册自定义降级响应"""
        self.fallbacks[skill_id] = fallback


# 全局单例
fallback_manager = FallbackManager()


# ==========================================
# 带降级的调用包装器
# ==========================================
async def call_with_fallback(
        skill_id: str,
        primary_func: Callable,
        *args,
        fallback_func: Optional[Callable] = None,
        **kwargs
) -> Dict:
    """
    带降级的 Skill 调用

    先尝试主调用，失败后尝试降级调用，
    降级也失败则返回预设的友好提示
    """
    # 1. 尝试主调用
    try:
        return await primary_func(*args, **kwargs)
    except Exception as primary_error:
        logger.warning("primary_call_failed", skill_id=skill_id, error=str(primary_error))

    # 2. 尝试备用调用（如旧版本）
    if fallback_func:
        try:
            logger.info("trying_fallback", skill_id=skill_id)
            return await fallback_func(*args, **kwargs)
        except Exception as fallback_error:
            logger.error("fallback_call_failed", skill_id=skill_id, error=str(fallback_error))

    # 3. 返回预设降级响应
    logger.warning("using_static_fallback", skill_id=skill_id)
    return fallback_manager.get_fallback(skill_id)