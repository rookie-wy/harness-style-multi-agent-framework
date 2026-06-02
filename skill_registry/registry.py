"""
Skill 注册中心 - 完整版（含可靠性保障 + Redis 缓存）
提供 Skill 的注册、发现、批量获取、健康检查、熔断器管理功能
"""

from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
import json
import os
import httpx
from config.logger import get_logger

from ..resilience.retry import skill_retry, RetryPolicy
from ..resilience.circuit_breaker import (
    with_circuit_breaker,
    CircuitBreakerOpenError,
    breaker_registry,
)
from ..resilience.fallback import call_with_fallback, fallback_manager
from ..resilience.idempotency import idempotency_store
from ..infrastructure.redis_client import cache_set  # 新增 Redis 缓存

# ==========================================
# 日志
# ==========================================
logger = get_logger(__name__)

# ==========================================
# FastAPI 应用
# ==========================================
app = FastAPI(
    title="Skill Registry - 个人生活助手",
    description="企业级 Skill 注册中心，提供服务发现、批量加载、熔断降级、幂等保证",
    version="2.0.0"
)

# ==========================================
# 数据模型
# ==========================================
from pydantic import BaseModel
from typing import Literal

class BatchRequest(BaseModel):
    """批量获取 Skill 请求"""
    ids: List[str]

class ExecuteRequest(BaseModel):
    """Skill 执行请求"""
    params: dict = {}
    user_input: str = ""
    session_id: str = ""
    idempotency_key: Optional[str] = None
    run_mode: Literal["active", "shadow"] = "active"

# ==========================================
# 注册表文件路径
# ==========================================
REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "registry.json")

# ==========================================
# 项目根目录（用于拼接相对路径）
# ==========================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==========================================
# 注册表操作
# ==========================================
def load_registry() -> List[dict]:
    """加载 Skill 注册表"""
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("registry_file_not_found", path=REGISTRY_FILE)
        return []
    except json.JSONDecodeError as e:
        logger.error("registry_json_error", error=str(e))
        return []

def save_registry(registry: List[dict]) -> bool:
    """保存 Skill 注册表"""
    try:
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("registry_save_error", error=str(e))
        return False

def get_skill_meta(skill_id: str) -> Optional[dict]:
    """获取单个 Skill 元数据"""
    registry = load_registry()
    for s in registry:
        if s["skill_id"] == skill_id:
            return s
    return None

# ==========================================
# 健康检查
# ==========================================
@app.get("/health")
async def health_check():
    """
    注册中心健康检查

    返回当前所有 Skill 的统计信息
    """
    registry = load_registry()

    active_skills = [s for s in registry if s["status"] == "active"]
    shadow_skills = [s for s in registry if s["status"] == "shadow"]
    deprecated_skills = [s for s in registry if s["status"] == "deprecated"]

    breaker_status = await breaker_registry.get_status()  # 改为 await
    open_breakers = [sid for sid, b in breaker_status.items() if b.get("state") == "OPEN"]

    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "skills": {
            "total": len(registry),
            "active": len(active_skills),
            "shadow": len(shadow_skills),
            "deprecated": len(deprecated_skills),
            "active_list": [s["skill_id"] for s in active_skills],
            "shadow_list": [s["skill_id"] for s in shadow_skills]
        },
        "circuit_breakers": {
            "total": len(breaker_status),
            "open": len(open_breakers),
            "open_list": open_breakers
        }
    }

# ==========================================
# Skill 列表（轻量级，用于路由）
# ==========================================
@app.get("/skills/list")
async def list_skills(
    status: str = Query("active,shadow", description="过滤状态，逗号分隔")
):
    """
    返回轻量级 Skill 列表

    用途：中控智能体路由判断
    只包含 name + description + triggers，不包含完整内容
    避免上下文污染
    """
    allowed_status = [s.strip() for s in status.split(",")]
    registry = load_registry()

    skills = []
    for s in registry:
        if s["status"] not in allowed_status:
            continue

        skills.append({
            "skill_id": s["skill_id"],
            "name": s["name"],
            "description": s["description"],
            "triggers": s.get("triggers", []),
            "status": s["status"],
            "version": s.get("version", "1.0.0"),
            "circuit_breaker": await breaker_registry.get_status(s["skill_id"])  # 改为 await
        })

    # 写入 Redis 缓存（30秒过期）
    await cache_set("skills:list", skills, ttl=30)
    logger.info("skills_listed", count=len(skills), status_filter=status)
    return skills

# ==========================================
# 批量获取 Skill 详情
# ==========================================
@app.post("/skills/batch")
async def batch_get_skills(request: BatchRequest):
    """
    批量获取 Skill 完整信息

    返回 schema.json + skill.md + mcp_profile.json 的完整内容
    用于构建 LangGraph ToolNode
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")

    if len(request.ids) > 10:
        raise HTTPException(status_code=400, detail="单次最多获取 10 个 Skill")

    registry = load_registry()
    skill_map = {s["skill_id"]: s for s in registry}

    skills_detail = []
    failed_skills = []

    for skill_id in request.ids:
        if skill_id not in skill_map:
            failed_skills.append({"skill_id": skill_id, "reason": "Skill 不存在"})
            continue

        meta = skill_map[skill_id]

        try:
            # 检查熔断器状态
            if await breaker_registry.is_open(skill_id):  # 改为 await
                failed_skills.append({
                    "skill_id": skill_id,
                    "reason": "熔断器已打开，Skill 暂时不可用"
                })
                continue

            # 加载 schema.json（用 PROJECT_ROOT 拼接绝对路径）
            schema_rel = meta.get("schema_path", "")
            schema_full = os.path.join(PROJECT_ROOT, schema_rel) if schema_rel else ""
            if not schema_full or not os.path.exists(schema_full):
                failed_skills.append({"skill_id": skill_id, "reason": f"schema.json 不存在: {schema_full}"})
                continue

            with open(schema_full, "r", encoding="utf-8") as f:
                schema = json.load(f)

            # 加载 skill.md
            md_rel = meta.get("md_path", "")
            md_full = os.path.join(PROJECT_ROOT, md_rel) if md_rel else ""
            md_content = ""
            if md_full and os.path.exists(md_full):
                with open(md_full, "r", encoding="utf-8") as f:
                    md_content = f.read()

            # 加载 mcp_profile.json
            mcp_profile = {}
            mcp_path = os.path.join(os.path.dirname(schema_full), "mcp_profile.json")
            if os.path.exists(mcp_path):
                with open(mcp_path, "r", encoding="utf-8") as f:
                    mcp_profile = json.load(f)

            skills_detail.append({
                "skill_id": skill_id,
                "name": meta.get("name", skill_id),
                "version": meta.get("version", "1.0.0"),
                "status": meta.get("status", "active"),
                "semantic": schema.get("semantic", {}),
                "interface": schema.get("interface", {}),
                "md_content": md_content,
                "mcp_profile": mcp_profile,
                "server_url": meta.get("server_url", ""),
                "execution_config": {
                    "timeout_ms": meta.get("timeout_ms", 30000),
                    "max_retries": meta.get("max_retries", 3),
                    "idempotent": meta.get("idempotent", False)
                }
            })

        except Exception as e:
            logger.error("skill_load_error", skill_id=skill_id, error=str(e))
            failed_skills.append({
                "skill_id": skill_id,
                "reason": f"加载失败: {str(e)}"
            })

    logger.info(
        "batch_load_complete",
        requested=len(request.ids),
        loaded=len(skills_detail),
        failed=len(failed_skills)
    )

    return {
        "skills": skills_detail,
        "failed": failed_skills,
        "total_requested": len(request.ids),
        "total_loaded": len(skills_detail)
    }

# ==========================================
# Skill 执行（核心端点，集成所有可靠性保障）
# ==========================================
@app.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, request: ExecuteRequest):
    """
    执行 Skill - 完整可靠性保障

    流程：
    1. 幂等性检查（防止重复执行）
    2. 熔断器检查（防止雪崩）
    3. 带重试的远程调用
    4. 失败时降级响应
    5. Shadow 模式支持
    """
    start_time = __import__("time").time()

    idempotency_key = request.idempotency_key
    if idempotency_key:
        cached_result = idempotency_store.get_result(idempotency_key)
        if cached_result:
            logger.info("idempotent_cache_hit", skill_id=skill_id, key=idempotency_key)
            return cached_result

        if not idempotency_store.check_and_set(idempotency_key):
            logger.warning("duplicate_request", skill_id=skill_id, key=idempotency_key)
            return {
                "meta": {
                    "protocol_version": "2024-11-05",
                    "skill_id": skill_id,
                    "skill_version": "1.0.0",
                    "status": "error",
                    "error_code": "DUPLICATE_REQUEST",
                    "execution_time_ms": int((__import__("time").time() - start_time) * 1000)
                },
                "data": None,
                "display": "请勿重复提交相同请求",
                "hints": ["上一个相同请求正在处理中，请等待结果"]
            }

    meta = get_skill_meta(skill_id)
    if not meta:
        error_result = _build_error_response(skill_id, "UNKNOWN_SKILL", f"Skill {skill_id} 不存在", start_time)
        _finalize_idempotent(idempotency_key, error_result)
        return error_result

    if meta["status"] == "deprecated":
        error_result = _build_error_response(skill_id, "SKILL_DEPRECATED", f"Skill {skill_id} 已废弃", start_time)
        _finalize_idempotent(idempotency_key, error_result)
        return error_result

    server_url = meta.get("server_url", "")
    if not server_url:
        error_result = _build_error_response(skill_id, "NO_SERVER_URL", f"Skill {skill_id} 未配置服务地址", start_time)
        _finalize_idempotent(idempotency_key, error_result)
        return error_result

    # 检查熔断器（改为 await）
    if await breaker_registry.is_open(skill_id):
        logger.warning("circuit_breaker_open", skill_id=skill_id)
        fallback = fallback_manager.get_fallback(skill_id)
        fallback["meta"]["skill_id"] = skill_id
        fallback["meta"]["error_code"] = "CIRCUIT_OPEN"
        fallback["meta"]["execution_time_ms"] = int((__import__("time").time() - start_time) * 1000)
        _finalize_idempotent(idempotency_key, fallback)
        return fallback

    @skill_retry(
        max_attempts=meta.get("max_retries", 3),
        min_wait=1,
        max_wait=meta.get("max_retry_wait", 10)
    )
    async def primary_call():
        timeout = meta.get("timeout_ms", 30000) / 1000
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{server_url}/execute",
                json={"params": request.params, "user_input": request.user_input}
            )
            resp.raise_for_status()
            result = resp.json()
            _validate_mcp_format(result, skill_id)
            return result

    fallback_url = meta.get("fallback_url")

    async def fallback_call():
        if not fallback_url:
            raise Exception("无可用备用服务")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{fallback_url}/execute",
                json={"params": request.params, "user_input": request.user_input}
            )
            resp.raise_for_status()
            return resp.json()

    try:
        result = await call_with_fallback(
            skill_id=skill_id,
            primary_func=primary_call,
            fallback_func=fallback_call if fallback_url else None
        )

        # 成功：重置熔断器（改为 await）
        await breaker_registry.record_success(skill_id)

        if request.run_mode == "shadow":
            logger.info("shadow_execution", skill_id=skill_id)
            result = {
                "meta": {
                    "protocol_version": "2024-11-05",
                    "skill_id": skill_id,
                    "skill_version": meta.get("version", "1.0.0"),
                    "status": "success",
                    "execution_time_ms": int((__import__("time").time() - start_time) * 1000)
                },
                "data": None,
                "display": f"[影子运行] {skill_id} 执行完成",
                "hints": ["影子运行结果已记录"]
            }

        result["meta"]["execution_time_ms"] = int((__import__("time").time() - start_time) * 1000)
        _finalize_idempotent(idempotency_key, result)
        return result

    except CircuitBreakerOpenError:
        error_result = _build_error_response(skill_id, "CIRCUIT_OPEN", f"Skill {skill_id} 暂时不可用", start_time)
        _finalize_idempotent(idempotency_key, error_result)
        return error_result

    except Exception as e:
        # 记录失败（改为 await）
        await breaker_registry.record_failure(skill_id)
        logger.error("skill_execution_failed", skill_id=skill_id, error=str(e))
        error_result = _build_error_response(skill_id, "EXECUTION_FAILED", f"Skill {skill_id} 执行失败: {str(e)}", start_time)
        _finalize_idempotent(idempotency_key, error_result)
        return error_result

# ==========================================
# 熔断器管理 API
# ==========================================
@app.get("/circuit-breakers")
async def get_circuit_breakers():
    return {
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "breakers": await breaker_registry.get_status()
    }

@app.post("/circuit-breakers/{skill_id}/reset")
async def reset_circuit_breaker(skill_id: str):
    await breaker_registry.record_success(skill_id)
    logger.info("circuit_breaker_manual_reset", skill_id=skill_id)
    return {
        "message": f"熔断器 {skill_id} 已重置",
        "status": await breaker_registry.get_status(skill_id)
    }

@app.post("/circuit-breakers/reset-all")
async def reset_all_circuit_breakers():
    status_before = await breaker_registry.get_status()
    for skill_id in status_before:
        await breaker_registry.record_success(skill_id)
    logger.info("all_circuit_breakers_reset")
    return {
        "message": "所有熔断器已重置",
        "status_before": status_before,
        "status_after": await breaker_registry.get_status()
    }

# ==========================================
# 辅助函数
# ==========================================
def _validate_mcp_format(result: dict, skill_id: str):
    if "meta" not in result:
        logger.warning("mcp_validation_failed", skill_id=skill_id, reason="missing meta")
        return
    meta = result["meta"]
    if meta.get("status") not in ("success", "partial", "error"):
        logger.warning("mcp_validation_failed", skill_id=skill_id, reason=f"invalid status: {meta.get('status')}")
    if "display" not in result:
        logger.warning("mcp_validation_failed", skill_id=skill_id, reason="missing display")

def _build_error_response(skill_id: str, error_code: str, message: str, start_time: float) -> dict:
    return {
        "meta": {
            "protocol_version": "2024-11-05",
            "skill_id": skill_id,
            "skill_version": "unknown",
            "status": "error",
            "error_code": error_code,
            "execution_time_ms": int((__import__("time").time() - start_time) * 1000)
        },
        "data": None,
        "display": message,
        "hints": ["请稍后重试"]
    }

def _finalize_idempotent(key: Optional[str], result: dict):
    if key:
        idempotency_store.mark_completed(key, result)

# ==========================================
# 启动事件
# ==========================================
@app.on_event("startup")
async def startup_event():
    registry = load_registry()
    for skill in registry:
        await breaker_registry.register(
            skill_id=skill["skill_id"],
            failure_threshold=skill.get("failure_threshold", 5),
            recovery_timeout=skill.get("recovery_timeout", 30)
        )
    # 写入 Redis 缓存
    skills_list = [
        {
            "skill_id": s["skill_id"],
            "name": s["name"],
            "description": s["description"],
            "triggers": s.get("triggers", []),
            "status": s["status"],
            "version": s.get("version", "1.0.0"),
            "circuit_breaker": await breaker_registry.get_status(s["skill_id"])
        }
        for s in registry
    ]
    await cache_set("skills:list", skills_list, ttl=30)
    logger.info("registry_startup_complete", skills_count=len(registry))

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("registry_shutting_down")