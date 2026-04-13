"""Тесты конфигурации оркестратора."""

import json
from pathlib import Path


def test_orchestrator_config_loads():
    """orchestrator.json должен загружаться без ошибок."""
    config_path = Path(__file__).parent.parent / "config" / "orchestrator.json"
    with open(config_path) as f:
        config = json.load(f)
    assert "version" in config
    assert "agents" in config
    assert "workflows" in config


def test_all_agents_defined():
    """Все 8 агентов должны быть в конфиге."""
    config_path = Path(__file__).parent.parent / "config" / "orchestrator.json"
    with open(config_path) as f:
        config = json.load(f)
    agent_ids = {a["id"] for a in config["agents"]}
    expected = {
        "researcher",
        "analyst",
        "author",
        "critic",
        "verifier",
        "legal_expert",
        "formatter",
        "calculator",
    }
    assert agent_ids == expected


def test_workflows_reference_valid_agents():
    """Pipeline'ы в workflows должны ссылаться на существующие агенты."""
    config_path = Path(__file__).parent.parent / "config" / "orchestrator.json"
    with open(config_path) as f:
        config = json.load(f)
    agent_ids = {a["id"] for a in config["agents"]}
    for wf_name, wf in config["workflows"].items():
        for agent_id in wf["pipeline"]:
            assert agent_id in agent_ids, (
                f"Workflow '{wf_name}' ссылается на несуществующий агент '{agent_id}'"
            )
