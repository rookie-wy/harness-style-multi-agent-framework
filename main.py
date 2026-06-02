"""企业版测试"""
import asyncio
from src.central_agent.orchestrator import LifeAssistantOrchestrator

async def main():
    assistant = LifeAssistantOrchestrator()

    print("=" * 60)
    print("测试 1: 知识检索 - 用户偏好")
    result = await assistant.process("我喜欢喝什么？", user_id=1)
    print(f"回复: {result}")

    print("\n" + "=" * 60)
    print("测试 2: 知识 + Skill")
    result = await assistant.process("我今天想去健身，算一下离下次健身还有几天，顺便提醒我晚上7点出发", user_id=1)
    print(f"回复: {result}")

    print("\n" + "=" * 60)
    print("测试 3: 添加新知识")
    assistant.add_user_knowledge("用户最近在学习 Rust 编程语言，每天晚上9点到11点学习", user_id=1)
    result = await assistant.process("我晚上9点有什么安排？", user_id=1)
    print(f"回复: {result}")

    await assistant.close()

if __name__ == "__main__":
    asyncio.run(main())