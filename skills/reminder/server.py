from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timedelta
import time
import re

app = FastAPI(title="Reminder Skill")

reminders: list[dict] = []


class ExecuteRequest(BaseModel):
    params: dict = {}
    user_input: str = ""


def extract_reminder_info(text: str) -> tuple[str, int]:
    """从用户输入中提取提醒内容和延迟时间"""
    content = text
    delay = 5

    patterns = [
        (r'(\d+)\s*分钟?\s*(?:后|以后)?\s*(?:提醒|叫我|喊我|通知)?\s*(.+)', lambda m: (m.group(2), int(m.group(1)))),
        (r'(?:提醒|叫我|喊我|通知)?\s*(.+?)\s*(\d+)\s*分钟?\s*(?:后|以后)?', lambda m: (m.group(1), int(m.group(2)))),
        (r'(\d+)\s*(?:小时|h)', lambda m: ("提醒事项", int(m.group(1)) * 60)),
    ]

    for pattern, extractor in patterns:
        match = re.search(pattern, text)
        if match:
            content, delay = extractor(match)
            break

    return content.strip(), delay


@app.get("/health")
async def health():
    return {"status": "healthy", "skill": "reminder", "pending": len(reminders)}


@app.post("/execute")
async def execute(request: ExecuteRequest):
    start = time.time()

    content = request.params.get("content", "")
    delay = request.params.get("delay_minutes", 0)

    if not content:
        content, delay = extract_reminder_info(request.user_input)

    if delay <= 0:
        delay = 5

    reminder = {
        "id": len(reminders) + 1,
        "content": content,
        "created_at": datetime.now().isoformat(),
        "trigger_at": (datetime.now() + timedelta(minutes=delay)).isoformat(),
        "delay_minutes": delay,
        "status": "scheduled"
    }
    reminders.append(reminder)

    return {
        "meta": {"protocol_version": "2024-11-05", "skill_id": "reminder",
                 "skill_version": "1.0.0", "status": "success",
                 "execution_time_ms": int((time.time() - start) * 1000)},
        "data": {"reminder_id": reminder["id"], "content": content, "trigger_at": reminder["trigger_at"]},
        "display": f"已设置提醒：{delay}分钟后提醒你「{content}」",
        "hints": []
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8012)