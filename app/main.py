from contextlib import asynccontextmanager
from uuid import uuid4
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from agents import Runner
from app.config import settings
from app.db import SessionLocal, TaskRecord, init_db
from app.agent_factory import build_team, load_registry
@asynccontextmanager
async def lifespan(app):
    init_db(); app.state.director=None
    if settings.openai_api_key: app.state.director, app.state.team=build_team()
    yield
app=FastAPI(title="Директор OpenAI",version="0.1.0",lifespan=lifespan)
@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "index.html")

class TaskRequest(BaseModel): instruction: str=Field(min_length=5,max_length=12000)
@app.get("/health")
def health(): return {"status":"ok","openai_configured":bool(settings.openai_api_key),"model":settings.openai_model}
@app.get("/agents")
def agents(): return [{"id":k,"name":v["name"],"description":v["description"]} for k,v in load_registry()["agents"].items()]
@app.get("/tasks")
def tasks():
    with SessionLocal() as db:
        rows=db.scalars(select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(100)).all()
        return [{"id":r.id,"instruction":r.instruction,"status":r.status,"result":r.result} for r in rows]
@app.post("/tasks")
async def create_task(payload:TaskRequest):
    if app.state.director is None: raise HTTPException(503,"OpenAI не настроен: задайте OPENAI_API_KEY")
    with SessionLocal() as db:
        active=db.scalar(select(func.count()).select_from(TaskRecord).where(TaskRecord.status=="running")) or 0
        if active>=settings.max_active_tasks: raise HTTPException(429,"Лимит активных задач достигнут")
        task_id=str(uuid4()); db.add(TaskRecord(id=task_id,instruction=payload.instruction,status="running")); db.commit()
    try:
        result=await Runner.run(app.state.director,payload.instruction); output=str(result.final_output); status="completed"
    except Exception as exc: output=f"{type(exc).__name__}: {exc}"; status="failed"
    with SessionLocal() as db:
        row=db.get(TaskRecord,task_id); row.status=status; row.result=output; db.commit()
    if status=="failed": raise HTTPException(502,output)
    return {"task_id":task_id,"status":status,"result":output}
