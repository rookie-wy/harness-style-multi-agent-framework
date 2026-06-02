"""
向量知识库 - 基于 ChromaDB
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 镜像站
os.environ["TRANSFORMERS_OFFLINE"] = "0"
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
from config.logger import get_logger
logger = get_logger(__name__)


class VectorKnowledgeBase:
    """向量知识库，存储和检索用户的个人知识"""

    def __init__(self, persist_dir: str = "./chroma_db", model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.model = SentenceTransformer(model_name)
        self.collection_name = "personal_knowledge"
        self._init_collection()

    def _init_collection(self):
        """初始化或获取 collection"""
        try:
            self.collection = self.client.get_collection(self.collection_name)
            logger.info("vector_collection_loaded", name=self.collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("vector_collection_created", name=self.collection_name)

    def add_knowledge(self, texts: List[str], metadatas: List[Dict] = None, ids: List[str] = None):
        """添加知识到向量库"""
        if not texts:
            return

        embeddings = self.model.encode(texts).tolist()

        if ids is None:
            existing_count = self.collection.count()
            ids = [f"kb_{existing_count + i}" for i in range(len(texts))]

        if metadatas is None:
            metadatas = [{"source": "manual"} for _ in texts]

        self.collection.add(embeddings=embeddings, documents=texts, metadatas=metadatas, ids=ids)
        logger.info("knowledge_added", count=len(texts))

    def search(self, query: str, top_k: int = 5, user_id: int = None) -> List[Dict]:
        """
        检索最相关的知识
        返回: [{"content": str, "score": float, "metadata": dict}, ...]
        """
        if self.collection.count() == 0:
            return []

        query_embedding = self.model.encode([query]).tolist()

        where_filter = None
        if user_id is not None:
            where_filter = {"user_id": str(user_id)}

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where=where_filter
        )

        knowledge_items = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                knowledge_items.append({
                    "content": doc,
                    "score": 1 - results["distances"][0][i] if results["distances"] else 0,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                })

        logger.info("knowledge_search", query=query[:50], results_count=len(knowledge_items))
        return knowledge_items

    def delete_by_user(self, user_id: int):
        """删除某个用户的所有知识"""
        try:
            self.collection.delete(where={"user_id": str(user_id)})
            logger.info("knowledge_deleted", user_id=user_id)
        except Exception as e:
            logger.error("knowledge_delete_failed", error=str(e))