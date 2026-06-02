"""全局测试配置"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from src.skill_registry.registry import app as registry_app
from src.skills.calculator.server import app as calculator_app
from src.skills.reminder.server import app as reminder_app
from src.skills.weather.server import app as weather_app
from src.skills.note.server import app as note_app

# ==========================================
# 异步事件循环
# ==========================================
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ==========================================
# 测试客户端 fixtures
# ==========================================
@pytest.fixture
async def registry_client():
    transport = ASGITransport(app=registry_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def calculator_client():
    transport = ASGITransport(app=calculator_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def reminder_client():
    transport = ASGITransport(app=reminder_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def weather_client():
    transport = ASGITransport(app=weather_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def note_client():
    transport = ASGITransport(app=note_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

# ==========================================
# 全局 mock
# ==========================================
@pytest.fixture
def mock_skill_registry_response():
    """模拟注册中心返回的 Skill 列表"""
    return [
        {"skill_id": "calculator", "name": "计算器",
         "description": "执行数学表达式计算", "triggers": ["计算", "算", "乘以", "除以"], "status": "active"},
        {"skill_id": "reminder", "name": "提醒助手",
         "description": "设置定时提醒", "triggers": ["提醒", "叫我", "别忘了"], "status": "active"},
        {"skill_id": "weather", "name": "天气查询",
         "description": "查询天气", "triggers": ["天气", "下雨", "温度"], "status": "shadow"},
        {"skill_id": "note", "name": "笔记助手",
         "description": "记录笔记", "triggers": ["记一下", "记录", "写下来"], "status": "active"},
    ]