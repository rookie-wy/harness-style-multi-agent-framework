"""天气子Agent - 封装天气查询Skill"""
from .base import BaseSubAgent
from typing import Dict, Any
import httpx
from src.config.settings import REGISTRY_URL
import asyncio

class WeatherAgent(BaseSubAgent):
    def __init__(self):
        super().__init__("weather")
        self.skill_id = "weather"

    async def execute(self, user_input: str, user_id: int,cached_params) -> Dict[str, Any]:
        if cached_params:
            city = cached_params.get("city", "成都")
        else:
            city = self._extract_city(user_input)
        city = self._extract_city(user_input)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{REGISTRY_URL}/skills/{self.skill_id}/execute",
                    json={"params": {"city": city}, "user_input": user_input, "user_id": user_id}
                )
                resp.raise_for_status()
                result = resp.json()

                # 保存成功经验
                if result.get("meta", {}).get("status") == "success":
                    from src.storage.experience_store import save_experience
                    asyncio.create_task(save_experience(user_input, self.name, {"city": city}, success=True))

                return {
                    "agent": self.name,
                    "display": result.get("display", ""),
                    "data": result.get("data", {}),
                    "status": result.get("meta", {}).get("status", "error")
                }
        except Exception as e:
            # 保存失败经验
            from src.storage.experience_store import save_experience
            asyncio.create_task(save_experience(user_input, self.name, {"city": city}, success=False))
            return {"agent": self.name, "display": f"天气查询失败: {str(e)}", "data": {}, "status": "error"}

    def _extract_city(self, text: str) -> str:
        cities = ["北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "武汉", "西安", "重庆"]
        for city in cities:
            if city in text:
                return city
        return "成都"