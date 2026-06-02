"""评估入口"""
import asyncio
from src.evaluation.evaluator import AgentEvaluator, default_cases
from src.central_agent.orchestrator import LifeAssistantOrchestrator

async def main():
    orch = LifeAssistantOrchestrator()
    evaluator = AgentEvaluator(orch)
    report = await evaluator.run(default_cases())
    evaluator.print_report(report)
    await orch.close()

asyncio.run(main())