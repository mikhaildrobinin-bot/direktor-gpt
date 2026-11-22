from pathlib import Path
import yaml
from agents import Agent
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "agents" / "registry.yaml"

# Full original prompts are the primary role instructions. The compact rules and
# long playbooks are appended as role context when present.
CONTEXT = {
    "director": ("director", None),
    "rp": ("rp", "rp"),
    "razvedchik": ("razvedchik", "razvedchik"),
    "issledovatel": ("issledovatel", "issledovatel"),
    "menedzher": ("menedzher", "menedzher"),
    "analitik": ("analitik", "analitik"),
    "arhitektor": ("arhitektor", "arhitektor"),
    "dizayner": ("dizayner", "dizayner"),
    "razrabotchik": ("razrabotchik", "razrabotchik"),
    "devops": ("devops", "devops"),
    "marketolog": ("marketolog", "marketolog"),
    "testirovshchik": ("testirovshchik", "testirovshchik"),
    "bezopasnik": ("bezopasnik", None),
    "auditor": ("auditor", None),
    "pharma-strateg": (None, None),
}

def load_registry():
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""

def _instructions(agent_id: str, prompt_path: str) -> str:
    sections = [_read_optional(ROOT / prompt_path)]
    rule_key, manual_key = CONTEXT.get(agent_id, (None, None))
    if rule_key:
        sections.append(_read_optional(ROOT / "agents/source/rules" / f"{rule_key}.md"))
    if manual_key:
        sections.append(_read_optional(ROOT / "agents/source/manuals" / f"{manual_key}.md"))
    return "\\n\\n---\\n\\n".join(x for x in sections if x.strip())

def build_team():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY не задан. Заполните .env перед запуском.")
    registry = load_registry()
    specialists = {}
    for agent_id, spec in registry["agents"].items():
        if agent_id in {"director", "rp"}:
            continue
        specialists[agent_id] = Agent(
            name=spec["name"],
            instructions=_instructions(agent_id, spec["prompt"]),
            model=settings.openai_model,
        )
    specialist_tools = [
        agent.as_tool(
            tool_name=f"delegate_{agent_id}",
            tool_description=registry["agents"][agent_id]["description"],
        )
        for agent_id, agent in specialists.items()
    ]
    rp_spec = registry["agents"]["rp"]
    rp = Agent(
        name=rp_spec["name"],
        instructions=_instructions("rp", rp_spec["prompt"]),
        model=settings.openai_model,
        tools=specialist_tools,
    )
    director_spec = registry["agents"]["director"]
    director = Agent(
        name=director_spec["name"],
        instructions=_instructions("director", director_spec["prompt"]),
        model=settings.openai_model,
        tools=[
            rp.as_tool(
                tool_name="delegate_to_project_manager",
                tool_description="Передать задачу руководителю проекта для декомпозиции, выбора специалистов и контроля результата.",
            )
        ],
    )
    return director, {"rp": rp, **specialists}
