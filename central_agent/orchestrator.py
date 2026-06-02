"""中控智能体 - LangGraph 编排 + 向量知识检索 + 对话历史"""
import sys
import os
from typing import TypedDict, List, Dict
import httpx
import asyncio
from langgraph.graph import StateGraph, END
from config.logger import get_logger

SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from knowledge.vector_store import VectorKnowledgeBase

logger = get_logger(__name__)

# 本地关键词兜底
FALLBACK_TRIGGERS = {
    "calculator": ["计算", "算", "+", "-", "*", "/", "等于", "多少"],
    "reminder": ["提醒", "叫我", "别忘了"],
    "weather": ["天气", "下雨", "温度", "几度", "带伞"],
    "note": ["记一下", "记录", "笔记", "写下来"],
}


class AssistantState(TypedDict):
    user_input: str
    user_id: int
    session_id: str
    available_skills: List[dict]
    routed_skills: List[str]
    tool_definitions: List[dict]
    tool_results: List[dict]
    knowledge_context: str
    final_response: str
    error: str | None
    chat_history: List[dict]


class LifeAssistantOrchestrator:

    def __init__(self, registry_url: str = "http://localhost:8001", chroma_dir: str = "./chroma_db"):
        self.registry_url = registry_url
        self.knowledge_base = VectorKnowledgeBase(persist_dir=chroma_dir)
        self.graph = self._build_graph()

    def _get_client(self):
        return httpx.AsyncClient(timeout=30.0, base_url=self.registry_url)

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AssistantState)

        graph.add_node("retrieve_knowledge", self.retrieve_knowledge_node)
        graph.add_node("router", self.router_node)
        graph.add_node("load_tools", self.load_tools_node)
        graph.add_node("executor", self.executor_node)
        graph.add_node("digest", self.digest_node)
        graph.add_node("error_handler", self.error_handler_node)

        graph.set_entry_point("retrieve_knowledge")
        graph.add_edge("retrieve_knowledge", "router")

        graph.add_conditional_edges(
            "router", self._after_router,
            {"load_tools": "load_tools", "digest": "digest", "error": "error_handler"}
        )
        graph.add_edge("load_tools", "executor")
        graph.add_edge("executor", "digest")
        graph.add_edge("digest", END)
        graph.add_edge("error_handler", END)

        return graph.compile()

    # ==========================================
    # 节点 1：向量知识检索
    # ==========================================
    async def retrieve_knowledge_node(self, state: AssistantState) -> AssistantState:
        logger.info("retrieve_knowledge_start", user_id=state.get("user_id"))

        try:
            results = self.knowledge_base.search(
                query=state["user_input"],
                top_k=3,
                user_id=state.get("user_id")
            )

            if results:
                knowledge_items = [r["content"] for r in results if r["score"] > 0.3]
                state["knowledge_context"] = "\n".join(knowledge_items)
                logger.info("knowledge_retrieved", count=len(knowledge_items))
            else:
                state["knowledge_context"] = ""
        except Exception as e:
            state["knowledge_context"] = ""
            logger.warning("knowledge_retrieve_failed", error=str(e))

        return state

    # ==========================================
    # 节点 2：路由
    # ==========================================
    async def router_node(self, state: AssistantState) -> AssistantState:
        logger.info("router_start")

        try:
            async with self._get_client() as client:
                resp = await client.get("/skills/list")
                resp.raise_for_status()
                state["available_skills"] = resp.json()

            matched = []
            user_input = state["user_input"]

            for skill in state["available_skills"]:
                for trigger in skill.get("triggers", []):
                    if trigger in user_input:
                        matched.append(skill)
                        break

            if not matched:
                for skill_id, triggers in FALLBACK_TRIGGERS.items():
                    for trigger in triggers:
                        if trigger in user_input:
                            online = any(
                                s["skill_id"] == skill_id and s["status"] == "active"
                                for s in state["available_skills"]
                            )
                            if online:
                                matched.append({"skill_id": skill_id, "name": skill_id})
                                break

            state["routed_skills"] = [s["skill_id"] for s in matched]

            if state.get("knowledge_context"):
                logger.info("router_with_context", context_len=len(state["knowledge_context"]))

        except Exception as e:
            state["error"] = f"路由失败: {e}"

        logger.info("router_result", routed=state["routed_skills"], user_input=state["user_input"][:30])
        return state

    def _after_router(self, state: AssistantState) -> str:
        if state.get("error"):
            return "error"
        if not state.get("routed_skills"):
            return "digest"
        return "load_tools"

    # ==========================================
    # 节点 3：加载工具
    # ==========================================
    async def load_tools_node(self, state: AssistantState) -> AssistantState:
        try:
            async with self._get_client() as client:
                resp = await client.post(
                    "/skills/batch",
                    json={"ids": state["routed_skills"]}
                )
                resp.raise_for_status()
                skills_data = resp.json()

            if isinstance(skills_data, list):
                state["tool_definitions"] = skills_data
            elif isinstance(skills_data, dict) and "skills" in skills_data:
                state["tool_definitions"] = skills_data["skills"]
            else:
                state["tool_definitions"] = []
        except Exception as e:
            state["error"] = f"加载工具失败: {e}"
            state["tool_definitions"] = []

        logger.info("load_tools_result", tools_count=len(state.get("tool_definitions", [])), error=state.get("error"))
        return state

    # ==========================================
    # 节点 4：并行执行
    # ==========================================
    async def executor_node(self, state: AssistantState) -> AssistantState:
        async def call_one(tool: dict) -> dict:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.registry_url}/skills/{tool['skill_id']}/execute",
                        json={"params": {}, "user_input": state["user_input"]}
                    )
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                return {"meta": {"status": "error"}, "display": str(e), "hints": []}

        tasks = [call_one(t) for t in state["tool_definitions"]]
        state["tool_results"] = await asyncio.gather(*tasks, return_exceptions=True)

        first = ""
        if state.get("tool_results") and isinstance(state["tool_results"][0], dict):
            first = state["tool_results"][0].get("display", "")[:50]
        logger.info("executor_result", results_count=len(state.get("tool_results", [])), first_display=first or "empty")
        return state

    # ==========================================
    # 节点 5：整合结果
    # ==========================================
    async def digest_node(self, state: AssistantState) -> AssistantState:
        logger.info("digest_start", tool_results=bool(state.get("tool_results")),
                    knowledge=bool(state.get("knowledge_context")))

        displays = []
        for r in state.get("tool_results", []):
            if isinstance(r, dict):
                d = r.get("display", "")
                if d:
                    displays.append(d)

        if displays:
            state["final_response"] = "\n".join(displays)
            return state

        return await self._llm_reply(state)

    # ==========================================
    # LLM 回复（带对话历史）
    # ==========================================
    async def _llm_reply(self, state: AssistantState) -> AssistantState:
        import json
        from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

        knowledge = state.get("knowledge_context", "")
        user_input = state["user_input"]

        system_prompt = "你是个人生活助手，回复简洁友好。记住对话上下文，能理解代词指代。"
        if knowledge:
            system_prompt += f" 你知道以下用户信息：{knowledge}"

        messages = [{"role": "system", "content": system_prompt}]

        for msg in state.get("chat_history", [])[-10:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

        messages.append({"role": "user", "content": user_input})

        logger.info("llm_reply_start", messages_count=len(messages), user_input=user_input[:30])

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{LLM_BASE_URL}/v1/chat/completions",
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 512
                    },
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json"
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                state["final_response"] = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("llm_reply_failed", error=str(e))
            if knowledge:
                state["final_response"] = f"根据我的记忆：{knowledge}"
            else:
                state["final_response"] = "我是你的生活助手，有什么可以帮你的吗？"

        return state

    # ==========================================
    # 节点 6：错误处理
    # ==========================================
    async def error_handler_node(self, state: AssistantState) -> AssistantState:
        state["final_response"] = f"抱歉，出错了：{state.get('error', '未知错误')}"
        return state

    # ==========================================
    # 对外接口
    # ==========================================
    async def process(self, user_input: str, user_id: int = 1, session_id: str = "default", chat_history: List[dict] = None) -> str:
        state = {
            "user_input": user_input,
            "user_id": user_id,
            "session_id": session_id,
            "available_skills": [],
            "routed_skills": [],
            "tool_definitions": [],
            "tool_results": [],
            "knowledge_context": "",
            "final_response": "",
            "error": None,
            "chat_history": chat_history or []
        }
        result = await self.graph.ainvoke(state)
        return result["final_response"]

    def add_user_knowledge(self, content: str, user_id: int = 1, metadata: dict = None):
        if metadata is None:
            metadata = {"user_id": str(user_id), "source": "user_input"}
        else:
            metadata["user_id"] = str(user_id)
        self.knowledge_base.add_knowledge(texts=[content], metadatas=[metadata])



if __name__ == "__main__":
    orch = LifeAssistantOrchestrator()
    graph = orch.graph
    png_data = graph.get_graph().draw_mermaid_png()
    with open("agent_graph.png", "wb") as f:
        f.write(png_data)
    print("✅ 图已保存为 agent_graph.png")