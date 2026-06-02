"""
个人生活助手 - Streamlit 前端（LangGraph 编排 + Redis 缓存 + 持久化记忆 + 百度天气）
"""
import streamlit as st
import asyncio
import sys
import os
import httpx
import json
from uuid import uuid4
from datetime import datetime, timedelta
from resilience.rate_limiter import check_rate_limit_sync

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SRC_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from memory.store import (
    save_message_sync,
    load_messages_sync,
    clear_messages_sync,
    get_or_create_user_sync,
)
from central_agent.orchestrator import LifeAssistantOrchestrator
from infrastructure.redis_client import get_sync_redis

st.set_page_config(page_title="个人生活助手", page_icon="🤖", layout="centered", initial_sidebar_state="expanded")

st.markdown("""<style>
    .status-ok { color: #2e7d32; font-weight: bold; }
    .status-err { color: #c62828; font-weight: bold; }
</style>""", unsafe_allow_html=True)

st.title("🤖 个人生活助手")
st.caption("基于 Harness 架构 | LangGraph 编排 | DeepSeek 驱动 | 流式输出")

REGISTRY_URL = "http://localhost:8001"


def get_cached_skill_list() -> list:
    """从 Redis 获取缓存的 Skill 列表（同步）"""
    try:
        r = get_sync_redis()
        data = r.get("skills:list")
        if data:
            return json.loads(data)
    except Exception:
        pass
    # Redis 未命中，降级为直接请求注册中心
    try:
        resp = httpx.get(f"{REGISTRY_URL}/skills/list", timeout=3)
        if resp.status_code == 200:
            skills = resp.json()
            # 回写 Redis
            try:
                r = get_sync_redis()
                r.setex("skills:list", 30, json.dumps(skills, ensure_ascii=False))
            except:
                pass
            return skills
    except:
        pass
    return []


@st.cache_data(ttl=30)
def get_cached_health() -> dict:
    try:
        resp = httpx.get(f"{REGISTRY_URL}/health", timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {"status": "offline"}


# ==========================================
# 会话管理（Cookie + Redis）
# ==========================================
SESSION_TTL = 24 * 3600  # 24小时


def get_or_create_session() -> tuple:
    """返回 (session_id, user_id)"""
    r = get_sync_redis()

    # 1. 从 Cookie 读取 session_id
    if "session_id" in st.context.cookies:
        session_id = st.context.cookies["session_id"]
        user_id_str = r.hget(f"session:{session_id}", "user_id")
        if user_id_str:
            # 刷新过期时间
            r.expire(f"session:{session_id}", SESSION_TTL)
            return session_id, int(user_id_str)

    # 2. 没有有效会话，创建新用户和会话
    user_id = get_or_create_user_sync()
    session_id = str(uuid4())[:12]

    # 存 Redis
    r.hset(f"session:{session_id}", mapping={
        "user_id": str(user_id),
        "created_at": datetime.now().isoformat()
    })
    r.expire(f"session:{session_id}", SESSION_TTL)

    # 写 Cookie（通过 st.query_params 中转，Streamlit 不支持直接写 Cookie）
    st.query_params["_sid"] = session_id
    st.rerun()
    return session_id, user_id  # 实际不会执行到这，rerun 会中断


# 从 Cookie 或 URL 获取 session_id
if "_sid" in st.query_params:
    session_id = st.query_params["_sid"]
    r = get_sync_redis()
    user_id_str = r.hget(f"session:{session_id}", "user_id")
    if user_id_str:
        USER_ID = int(user_id_str)
        # 刷新过期
        r.expire(f"session:{session_id}", SESSION_TTL)
    else:
        session_id, USER_ID = get_or_create_session()
else:
    session_id, USER_ID = get_or_create_session()

# ==========================================
# 初始化 LangGraph 编排器（全局单例）
# ==========================================
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = LifeAssistantOrchestrator(
        registry_url=REGISTRY_URL,
        chroma_dir=os.path.join(SRC_DIR, "chroma_db")
    )

# ==========================================
# 加载历史消息（同步版本）
# ==========================================
if "messages" not in st.session_state:
    try:
        loaded = load_messages_sync(USER_ID)
        st.session_state.messages = loaded if loaded else []
    except:
        st.session_state.messages = []

if "pending_input" not in st.session_state:
    st.session_state.pending_input = None

# ==========================================
# 侧边栏
# ==========================================
with st.sidebar:
    st.header("⚙️ 系统状态")
    health = get_cached_health()
    skill_list = get_cached_skill_list()
    active_skills = [s for s in skill_list if s.get("status") == "active"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总数", len(skill_list))
    with col2:
        st.metric("在线", len(active_skills))
    with col3:
        if health.get("status") == "healthy":
            st.markdown('<span class="status-ok">● 正常</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-err">● 离线</span>', unsafe_allow_html=True)

    st.divider()
    with st.expander("📋 系统日志 (最近50条)"):
        try:
            log_path = os.path.join(SRC_DIR, "logs", "agent.log")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-50:]  # 最近50行
                for line in lines:
                    st.text(line.strip())
            else:
                st.caption("暂无日志文件")
        except Exception:
            st.caption("日志读取失败")
    st.header("🛠️ 可用技能")
    for s in skill_list:
        icon = "✅" if s["status"] == "active" else "👀"
        st.markdown(f"{icon} **{s['name']}**")

    st.divider()
    st.header("💡 试试这些")
    examples = [
        "今天天气怎么样",
        "今天北京天气怎么样",
        "南京的呢",
        "算一下 (35-2+4)/23",
        "3分钟后提醒我喝水",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"btn_{ex}"):
            st.session_state.pending_input = ex
            st.rerun()

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ 清除", use_container_width=True, key="btn_clear"):
            clear_messages_sync(USER_ID)
            st.session_state.messages = []
            st.cache_data.clear()
            st.rerun()
    with col_b:
        if st.button("🔄 刷新", use_container_width=True, key="btn_refresh"):
            st.cache_data.clear()
            st.rerun()

# ==========================================
# 显示历史
# ==========================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
        if msg["role"] == "user":
            st.code(msg["content"], language=None)
        else:
            st.write(msg["content"])

# ==========================================
# 处理输入
# ==========================================
pending = st.session_state.get("pending_input")
if pending:
    prompt = pending
    st.session_state.pending_input = None
else:
    prompt = None

user_input = st.chat_input("输入你的需求...")
final_input = user_input or prompt

if final_input:
    # 限流检查
    if not check_rate_limit_sync(USER_ID):
        with st.chat_message("assistant", avatar="🤖"):
            st.error("请求太频繁，请稍后重试。")
        st.stop()
    with st.chat_message("user", avatar="👤"):
        st.code(final_input, language=None)
    st.session_state.messages.append({"role": "user", "content": final_input})
    save_message_sync(USER_ID, "user", final_input)

    with st.chat_message("assistant", avatar="🤖"):
        placeholder = st.empty()
        placeholder.write("⏳ 处理中...")

        try:
            orch = st.session_state.orchestrator
            response = asyncio.run(orch.process(
                final_input,
                USER_ID,
                chat_history=st.session_state.messages
            ))

            placeholder.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            save_message_sync(USER_ID, "assistant", response)

        except Exception as e:
            placeholder.error(f"抱歉，出错了：{str(e)}")

st.divider()
st.caption(f"🔑 用户 #{USER_ID}  |  💬 {len(st.session_state.get('messages', []))} 条消息")
st.caption("个人生活助手 v1.0 | Harness 架构 | LangGraph 编排 | 流式输出")