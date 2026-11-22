from pathlib import Path
from app.agent_factory import CONTEXT, ROOT, _instructions, load_registry


def test_registry_contains_expected_team():
    agents = load_registry()["agents"]
    assert len(agents) == 15
    assert "director" in agents
    assert "rp" in agents


def test_all_prompt_files_exist_and_are_not_empty():
    for spec in load_registry()["agents"].values():
        prompt = ROOT / spec["prompt"]
        assert prompt.is_file()
        assert prompt.read_text(encoding="utf-8").strip()


def test_agent_names_are_unique():
    names = [spec["name"] for spec in load_registry()["agents"].values()]
    assert len(names) == len(set(names))


def test_role_context_files_are_loaded_when_present():
    registry = load_registry()["agents"]
    for agent_id, spec in registry.items():
        combined = _instructions(agent_id, spec["prompt"])
        assert combined.strip(), agent_id
        assert spec["name"]


def test_pharma_strateg_has_original_role_prompt():
    spec = load_registry()["agents"]["pharma-strateg"]
    combined = _instructions("pharma-strateg", spec["prompt"])
    assert "Фарма" in combined or "фарма" in combined.lower()
