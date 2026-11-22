from pathlib import Path
import yaml
from agents import Agent
from app.config import settings
ROOT = Path(__file__).resolve().parents[1]
def load_registry():
    with (ROOT / "agents/registry.yaml").open(encoding="utf-8") as f: return yaml.safe_load(f)
def build_team():
    if not settings.openai_api_key: raise RuntimeError("OPENAI_API_KEY не задан")
    registry = load_registry(); specialists = {}
    for key, spec in registry["agents"].items():
        if key in {"director", "rp"}: continue
        specialists[key] = Agent(name=spec["name"], instructions=(ROOT/spec["prompt"]).read_text(encoding="utf-8"), model=settings.openai_model)
    tools = [a.as_tool(tool_name=f"delegate_{key}", tool_description=registry["agents"][key]["description"]) for key,a in specialists.items()]
    rp_spec=registry["agents"]["rp"]
    rp=Agent(name=rp_spec["name"], instructions=(ROOT/rp_spec["prompt"]).read_text(encoding="utf-8"), model=settings.openai_model, tools=tools)
    d=registry["agents"]["director"]
    director=Agent(name=d["name"], instructions=(ROOT/d["prompt"]).read_text(encoding="utf-8"), model=settings.openai_model, tools=[rp.as_tool(tool_name="delegate_to_project_manager", tool_description="Передать задачу руководителю проекта")])
    return director, {"rp":rp, **specialists}
