from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import time

app = FastAPI(title="Note Skill")

notes: list[dict] = []


class ExecuteRequest(BaseModel):
    params: dict = {}
    user_input: str = ""


@app.get("/health")
async def health():
    return {"status": "healthy", "skill": "note", "total": len(notes)}


@app.post("/execute")
async def execute(request: ExecuteRequest):
    start = time.time()

    content = request.params.get("content", request.user_input)
    category = request.params.get("category", "general")

    note = {
        "id": len(notes) + 1,
        "content": content,
        "category": category,
        "created_at": datetime.now().isoformat()
    }
    notes.append(note)

    preview = content[:100] + ("..." if len(content) > 100 else "")

    return {
        "meta": {"protocol_version": "2024-11-05", "skill_id": "note",
                 "skill_version": "1.0.0", "status": "success",
                 "execution_time_ms": int((time.time() - start) * 1000)},
        "data": {"note_id": note["id"], "content": content, "category": category},
        "display": f"已记录：{preview}",
        "hints": []
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8014)