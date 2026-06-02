"""
健康检查器
定期检查所有 Skill 的健康状态
"""
import asyncio
import httpx
from typing import Dict, List
from datetime import datetime
from config.logger import get_logger
logger = get_logger(__name__)


class HealthChecker:
    """定期健康检查"""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.status: Dict[str, dict] = {}
        self._task: asyncio.Task = None

    async def check_skill(self, skill_id: str, url: str) -> dict:
        """检查单个 Skill"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/health")
                resp.raise_for_status()
                return {
                    "skill_id": skill_id,
                    "status": "healthy",
                    "response_time_ms": 0,
                    "last_check": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "skill_id": skill_id,
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }

    async def check_all(self, skills: List[dict]):
        """检查所有 Skill"""
        tasks = []
        for skill in skills:
            url = skill.get("server_url", "")
            if url:
                tasks.append(self.check_skill(skill["skill_id"], url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict):
                self.status[result["skill_id"]] = result

        healthy = sum(1 for s in self.status.values() if s["status"] == "healthy")
        unhealthy = len(self.status) - healthy

        if unhealthy > 0:
            logger.warning("health_check_failed", healthy=healthy, unhealthy=unhealthy)

    def start(self, skills: List[dict]):
        """启动定期检查"""

        async def _run():
            while True:
                await self.check_all(skills)
                await asyncio.sleep(self.check_interval)

        self._task = asyncio.create_task(_run())

    def stop(self):
        """停止检查"""
        if self._task:
            self._task.cancel()


# 全局单例
health_checker = HealthChecker()