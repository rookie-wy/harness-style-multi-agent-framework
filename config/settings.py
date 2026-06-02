"""全局配置"""
import os
from dotenv import load_dotenv
load_dotenv()
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8001")

SKILL_SERVERS = {
    "calculator": os.getenv("CALCULATOR_URL", "http://localhost:8011"),
    "reminder": os.getenv("REMINDER_URL", "http://localhost:8012"),
    "weather": os.getenv("WEATHER_URL", "http://localhost:8013"),
    "note": os.getenv("NOTE_URL", "http://localhost:8014"),
}

LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY")
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"


# JWT
JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM=os.getenv("JWT_ALGORITHM")
JWT_EXPIRE_MINUTES=1440

# 数据库 (开发用 SQLite，生产改 PostgreSQL)
DATABASE_URL=os.getenv("DATABASE_URL")
# 生产环境改为:
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/life_assistant

# 向量数据库
CHROMA_PERSIST_DIR=os.getenv("CHROMA_PERSIST_DIR")
EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL")

LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 4096
LLM_TOP_P = 0.9




RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))