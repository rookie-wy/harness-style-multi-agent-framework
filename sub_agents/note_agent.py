"""笔记子Agent - 封装笔记Skill"""
from .base import BaseSubAgent
from typing import Dict, Any
import httpx
from src.config.settings import REGISTRY_URL

class NoteAgent(BaseSubAgent):
    def __init__(self):
        super().__init__("note")
        self.skill_id = "note"

    async def execute(self, user_input: str, user_id: int) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{REGISTRY_URL}/skills/{self.skill_id}/execute",
                    json={"params": {}, "user_input": user_input}
                )
                resp.raise_for_status()
                result = resp.json()
                return {
                    "agent": self.name,
                    "display": result.get("display", ""),
                    "data": result.get("data", {}),
                    "status": result.get("meta", {}).get("status", "error")
                }
        except Exception as e:
            return {"agent": self.name, "display": f"笔记保存失败: {str(e)}", "data": {}, "status": "error"}