import pytest
from httpx import AsyncClient, ASGITransport
from src.skill_registry.registry import app

@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_list_skills():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/skills/list")
        assert resp.status_code == 200
        skills = resp.json()
        assert len(skills) >= 3

@pytest.mark.asyncio
async def test_batch_get():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/skills/batch", json={"ids": ["calculator"]})
        assert resp.status_code == 200
        skills = resp.json()
        assert len(skills) == 1
        assert skills[0]["skill_id"] == "calculator"