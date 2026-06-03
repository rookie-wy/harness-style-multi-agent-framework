"""子Agent基类"""
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseSubAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(self, user_input: str, user_id: int) -> Dict[str, Any]:
        """执行任务，返回结构化结果"""
        pass