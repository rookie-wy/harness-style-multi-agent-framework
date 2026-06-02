"""默认知识加载器"""
from .vector_store import VectorKnowledgeBase

DEFAULT_KNOWLEDGE = [
    {
        "content": "用户喜欢喝咖啡，每天早上需要一杯美式咖啡。",
        "metadata": {"category": "preference", "source": "user_profile"}
    },
    {
        "content": "用户每天下午3点有15分钟的休息时间，可以提醒喝水。",
        "metadata": {"category": "habit", "source": "user_profile"}
    },
    {
        "content": "用户的健身计划：每周一、三、五晚上7点去健身房。",
        "metadata": {"category": "schedule", "source": "user_profile"}
    },
    {
        "content": "记住用户的重要日期：妻子生日是3月15日，结婚纪念日是10月1日。",
        "metadata": {"category": "important_dates", "source": "user_profile"}
    }
]


def load_default_knowledge(vb: VectorKnowledgeBase, user_id: int = 1):
    """加载默认知识（仅首次初始化时使用）"""
    if vb.collection.count() > 0:
        return

    texts = [item["content"] for item in DEFAULT_KNOWLEDGE]
    metadatas = [{**item["metadata"], "user_id": str(user_id)} for item in DEFAULT_KNOWLEDGE]

    vb.add_knowledge(texts=texts, metadatas=metadatas)