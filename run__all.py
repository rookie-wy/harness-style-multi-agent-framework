"""一键启动所有服务"""
import config.logger
import subprocess
import sys
import time
import signal
import asyncio
from src.infrastructure.redis_client import health_check as redis_health

processes = []

def start_service(name: str, module: str, port: int):
    proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        f"{module}:app",
        "--host", "0.0.0.0", "--port", str(port), "--log-level", "info"
    ])
    processes.append((name, proc))
    print(f"✅ {name} 启动中... (端口 {port})")

def cleanup(signum, frame):
    print("\n⏳ 正在停止所有服务...")
    for name, proc in processes:
        proc.terminate()
        proc.wait()
        print(f"🛑 {name} 已停止")
    sys.exit(0)

async def init_system():
    """初始化数据库和向量知识库"""
    from src.storage.database import init_db
    from src.knowledge.vector_store import VectorKnowledgeBase
    from src.knowledge.knowledge_loader import load_default_knowledge

    print("📦 初始化数据库...")
    await init_db()
    print("✅ 数据库初始化完成")

    print("🧠 初始化向量知识库...")
    vb = VectorKnowledgeBase()
    load_default_knowledge(vb)
    print("✅ 向量知识库初始化完成")

    # 新增 Redis 检查
    print("🔴 检查 Redis 连接...")
    if await redis_health():
        print("✅ Redis 连接正常")
    else:
        print("⚠️  Redis 未连接，缓存功能将不可用")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("🚀 启动个人生活助手 (企业版)...")

    # 初始化
    asyncio.run(init_system())
    time.sleep(1)

    # 启动服务
    start_service("注册中心", "src.skill_registry.registry", 8001)
    time.sleep(1)
    start_service("Calculator", "src.skills.calculator.server", 8011)
    start_service("Reminder", "src.skills.reminder.server", 8012)
    start_service("Weather (Shadow)", "src.skills.weather.server", 8013)
    start_service("Note", "src.skills.note.server", 8014)

    print("\n📋 所有服务已启动:")
    print("  注册中心: http://localhost:8001")
    print("  Calculator: http://localhost:8011")
    print("  Reminder: http://localhost:8012")
    print("  Weather: http://localhost:8013")
    print("  Note: http://localhost:8014")
    print("\n🧠 向量知识库: ./chroma_db")
    print("💾 数据库: ./life_assistant.db")
    print("\n按 Ctrl+C 停止所有服务...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup(None, None)