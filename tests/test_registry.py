from pathlib import Path
from app.agent_factory import load_registry

def test_registry_contains_expected_team():
    agents = load_registry()["agents"]
    assert len(agents) == 15
    assert "director" in agents
    assert "rp" in agents

def test_all_prompt_files_exist():
    root = Path(__file__).resolve().parents[1]
    for spec in load_registry()["agents"].values():
        assert (root / spec["prompt"]).is_file()

def test_agent_names_are_unique():
    names = [spec["name"] for spec in load_registry()["agents"].values()]
    assert len(names) == len(set(names))
