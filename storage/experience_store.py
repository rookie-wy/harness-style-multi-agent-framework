"""
经验池存储 - SQLite + 向量相似度匹配
记录成功/失败的任务执行记录，用于后续相似查询的快速匹配
"""
import os
import json
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer
from src.config.logger import get_logger

logger = get_logger(__name__)

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "experience.db")

# 向量模型（轻量中文模型）
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")


async def init_experience_db():
    """初始化经验池表"""
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                params TEXT NOT NULL,
                embedding BLOB NOT NULL,
                success INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_skill ON experiences(skill_name)")
        await db.commit()


async def save_experience(query: str, skill_name: str, params: dict, success: bool = True):
    """保存经验到经验池"""
    import aiosqlite
    await init_experience_db()

    embedding = model.encode(query)
    embedding_bytes = embedding.tobytes()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO experiences (query, skill_name, params, embedding, success) VALUES (?, ?, ?, ?, ?)",
            (query, skill_name, json.dumps(params, ensure_ascii=False), embedding_bytes, 1 if success else 0)
        )
        await db.commit()
    logger.info("experience_saved", query=query[:30], skill=skill_name, success=success)


async def find_similar_experience(query: str, skill_name: str, threshold: float = 0.85) -> dict | None:
    """
    查找相似的历史成功经验
    返回匹配到的 params，如果没有匹配则返回 None
    """
    import aiosqlite
    await init_experience_db()

    query_embedding = model.encode(query)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, query, params, embedding FROM experiences WHERE skill_name = ? AND success = 1 ORDER BY created_at DESC LIMIT 50",
            (skill_name,)
        )
        rows = await cursor.fetchall()

    best_match = None
    best_similarity = 0.0

    for row in rows:
        exp_id, exp_query, params_str, embedding_bytes = row
        exp_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)

        # 余弦相似度
        similarity = np.dot(query_embedding, exp_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(exp_embedding)
        )

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = {
                "id": exp_id,
                "query": exp_query,
                "params": json.loads(params_str),
                "similarity": float(similarity)
            }

    if best_match and best_match["similarity"] >= threshold:
        logger.info("experience_matched", query=query[:30], matched_query=best_match["query"][:30], similarity=round(best_match["similarity"], 3))
        return best_match["params"]

    return None


async def clear_experiences(skill_name: str = None):
    """清除经验（按技能过滤）"""
    import aiosqlite
    await init_experience_db()
    async with aiosqlite.connect(DB_PATH) as db:
        if skill_name:
            await db.execute("DELETE FROM experiences WHERE skill_name = ?", (skill_name,))
        else:
            await db.execute("DELETE FROM experiences")
        await db.commit()