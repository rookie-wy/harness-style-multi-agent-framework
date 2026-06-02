"""Weather Skill - FastAPI 微服务（百度天气 API）"""
from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os
import sys
import time
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# FastAPI 应用（必须放在最前面）
# ==========================================
app = FastAPI(title="Weather Skill - 百度天气")

# ==========================================
# 路径配置
# ==========================================
SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from storage.database import async_session
    from storage.models import User
    from sqlalchemy import select, update
except ImportError:
    async_session = None
    User = None
    select = None
    update = None

# ==========================================
# 配置
# ==========================================
BAIDU_AK = os.getenv("BAIDU_MAP_AK")
BAIDU_WEATHER_URL = "https://api.map.baidu.com/weather/v1/"

DEFAULT_CITY = "成都"
DEFAULT_DISTRICT_ID = "510100"

# ==========================================
# 城市名 → 行政区划代码
# ==========================================
CITY_CODE_MAP = {
    "北京": "110100", "上海": "310000", "广州": "440100", "深圳": "440300",
    "成都": "510100", "杭州": "330100", "南京": "320100", "武汉": "420100",
    "西安": "610100", "重庆": "500000", "长沙": "430100", "郑州": "410100",
    "苏州": "320500", "天津": "120000", "青岛": "370200", "大连": "210200",
    "厦门": "350200", "福州": "350100", "合肥": "340100", "沈阳": "210100",
    "哈尔滨": "230100", "长春": "220100", "昆明": "530100", "贵阳": "520100",
    "南宁": "450100", "海口": "460100", "拉萨": "540100", "银川": "640100",
    "兰州": "620100", "西宁": "630100", "乌鲁木齐": "650100", "呼和浩特": "150100"
}

KNOWN_CITIES = list(CITY_CODE_MAP.keys())


# ==========================================
# 请求模型
# ==========================================
class ExecuteRequest(BaseModel):
    params: dict = {}
    user_input: str = ""
    user_id: int = 1


# ==========================================
# 数据库操作
# ==========================================
async def get_user_city(user_id: int) -> str:
    """从数据库获取用户默认城市"""
    try:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user and user.city:
                return user.city
    except Exception:
        pass
    return ""


async def save_user_city(user_id: int, city: str):
    """保存用户默认城市到数据库"""
    try:
        async with async_session() as db:
            await db.execute(
                update(User).where(User.id == user_id).values(city=city)
            )
            await db.commit()
    except Exception:
        pass


# ==========================================
# 城市提取
# ==========================================
def extract_city(text: str) -> str:
    """从用户输入中提取城市名"""
    for city in KNOWN_CITIES:
        if city in text:
            return city
    return ""


# ==========================================
# 百度天气 API
# ==========================================
async def fetch_weather(city: str) -> dict:
    """调用百度天气 API"""
    district_id = CITY_CODE_MAP.get(city, DEFAULT_DISTRICT_ID)
    params = {"ak": BAIDU_AK, "district_id": district_id, "data_type": "all"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(BAIDU_WEATHER_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def format_weather(api_data: dict, city: str) -> dict:
    """格式化天气数据"""
    if api_data.get("status") != 0:
        return _error("EXTERNAL_API_ERROR", f"天气查询失败: {api_data.get('message', '未知错误')}")

    result = api_data.get("result", {})
    now = result.get("now", {})
    forecasts = result.get("forecasts", [])
    today = forecasts[0] if forecasts else {}

    display = (
        f"📍 {city} 天气\n"
        f"🌡️ 当前: {now.get('temp', '?')}°C（体感 {now.get('feels_like', '?')}°C）\n"
        f"🌤️ {now.get('text', '?')}\n"
        f"💧 湿度: {now.get('rh', '?')}%\n"
        f"🌬️ {now.get('wind_dir', '?')} {now.get('wind_class', '?')}级\n"
        f"\n📅 今天: {today.get('text_day', '?')}，"
        f"最高 {today.get('high', '?')}°C，最低 {today.get('low', '?')}°C"
    )

    return {
        "meta": {
            "protocol_version": "2024-11-05",
            "skill_id": "weather",
            "skill_version": "1.0.0",
            "status": "success",
            "execution_time_ms": 0
        },
        "data": {
            "city": city,
            "temp": now.get("temp"),
            "weather": now.get("text"),
            "humidity": now.get("rh"),
            "wind": f"{now.get('wind_dir', '')} {now.get('wind_class', '')}级",
            "forecast_high": today.get("high"),
            "forecast_low": today.get("low"),
            "forecast_day": today.get("text_day"),
        },
        "display": display,
        "hints": []
    }


def _error(code: str, message: str) -> dict:
    return {
        "meta": {
            "protocol_version": "2024-11-05",
            "skill_id": "weather",
            "skill_version": "1.0.0",
            "status": "error",
            "error_code": code,
            "execution_time_ms": 0
        },
        "data": None,
        "display": message,
        "hints": ["请稍后重试"]
    }


# ==========================================
# API 端点
# ==========================================
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "skill": "weather",
        "version": "1.0.0",
        "api": "百度天气",
        "default_city": DEFAULT_CITY
    }


@app.post("/execute")
async def execute(request: ExecuteRequest):
    start = time.time()
    user_input = request.user_input
    user_id = request.user_id
    params = request.params

    # 1. 确定城市
    city = params.get("city", "")
    if not city:
        city = extract_city(user_input)
    if not city:
        city = await get_user_city(user_id)
    if not city:
        city = DEFAULT_CITY

    # 2. 查询非默认城市时询问
    saved_city = await get_user_city(user_id)
    if city != saved_city and city != DEFAULT_CITY and saved_city:
        return {
            "meta": {
                "protocol_version": "2024-11-05",
                "skill_id": "weather",
                "skill_version": "1.0.0",
                "status": "partial",
                "execution_time_ms": int((time.time() - start) * 1000)
            },
            "data": {"pending_city": city, "current_city": saved_city},
            "display": f"你查询的是「{city}」，当前默认城市是「{saved_city}」。需要把默认城市改为「{city}」吗？",
            "hints": ["回复'是'保存为新默认城市", "回复'否'保持当前默认城市"]
        }

    # 3. 处理确认
    confirm_words = {"是", "是的", "好", "可以", "行", "改", "确认", "保存", "要"}
    if user_input.strip() in confirm_words and "pending_city" in params:
        new_city = params["pending_city"]
        await save_user_city(user_id, new_city)
        return {
            "meta": {
                "protocol_version": "2024-11-05",
                "skill_id": "weather",
                "skill_version": "1.0.0",
                "status": "success",
                "execution_time_ms": int((time.time() - start) * 1000)
            },
            "data": {"saved_city": new_city},
            "display": f"✅ 默认城市已改为「{new_city}」。现在可以查询天气了。",
            "hints": [f"试试说'{new_city}今天天气怎么样'"]
        }

    # 4. 查询天气
    try:
        api_data = await fetch_weather(city)
        result = format_weather(api_data, city)
        result["meta"]["execution_time_ms"] = int((time.time() - start) * 1000)
        return result

    except httpx.TimeoutException:
        return _error("TIMEOUT", "天气服务响应超时")
    except Exception as e:
        return _error("EXTERNAL_API_ERROR", f"天气查询失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)