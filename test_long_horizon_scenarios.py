from __future__ import annotations

import json
from pathlib import Path

from maya_long_horizon import evaluate_scenario, evaluate_set, harden_scenario, render_scenario_set

ROOT = Path(__file__).resolve().parent

PROTOTYPES = [
    {
        "title": "Integrity and freedom path",
        "gains": ["real integrity", "compounding value", "alignment with Freedom and Growth", "depth and credibility"],
        "sacrifices": ["speed", "early financial return", "comfort", "rapid validation"],
        "trajectory": "A first year of quiet construction, research, design iteration, and philosophical work on opportunity.",
        "emotional_cost": "Isolation, uncertainty, burnout risk, and frustration when progress feels invisible.",
        "risks": ["over-engineering before validation", "insufficient rest", "limited external input"],
        "assumptions": ["the founder can sustain a slower pace", "the product remains useful while being rigorously developed"],
        "reversible_experiment": "Run one supporter demonstration and gather focused feedback before expanding the scope.",
    },
    {
        "title": "Research-backed craft path",
        "gains": ["depth", "credibility", "a differentiated research-backed product"],
        "sacrifices": ["speed", "early momentum", "short-term financial return"],
        "trajectory": "Long stretches of solitary research and iteration with occasional breakthroughs.",
        "emotional_cost": "Quiet frustration and sustained uncertainty with delayed validation.",
        "risks": ["building before users validate the need", "emotional weight of a high-stakes project"],
        "assumptions": ["research quality creates a meaningful advantage", "external feedback can be added before major expansion"],
        "reversible_experiment": "Test one narrow research-backed opportunity map with a real user and record corrections.",
    },
    {
        "title": "Integrated intellectual craft path",
        "gains": ["depth", "creative and technical integration", "meaning", "a novel and trustworthy system"],
        "sacrifices": ["launch speed", "early validation", "the simplicity of a narrow project"],
        "trajectory": "A slow accumulation of writing, design, research, and philosophy into a coherent system.",
        "emotional_cost": "Setbacks feel personal when the vision outpaces the tools.",
        "risks": ["scope expansion", "over-engineering", "isolation"],
        "assumptions": ["the founder can preserve rest and outside perspective", "the full intellectual range can become product value"],
        "reversible_experiment": "Create one small integrated prototype and ask two people which part produces clear value.",
    },
]


def main():
    before = {
        name: (ROOT / name).read_bytes() if (ROOT / name).exists() else b""
        for name in ("andy_profile.json", "maya_activation_state.json", "learning_status.json")
    }

    result = evaluate_set(PROTOTYPES)
    assert result["status"] == "ready_for_review"
    assert result["scenario_count"] == 3
    assert result["alternative_paths_present"] is True
    assert all(item["decision_owner"] == "human" for item in result["evaluations"])
    assert all(item["memory_update"] == "not_performed" for item in result["evaluations"])
    assert all(item["external_action"] == "not_performed" for item in result["evaluations"])

    rendered = render_scenario_set(PROTOTYPES)
    assert "not predictions" in rendered.lower()
    assert "human choice" in rendered.lower()

    unsafe = {
        "title": "Unsafe certainty example",
        "gains": ["success"],
        "sacrifices": ["time"],
        "trajectory": "This path will definitely become the right path.",
        "emotional_cost": "None.",
        "risks": ["none"],
        "assumptions": ["the outcome is guaranteed"],
        "reversible_experiment": "Commit immediately; this will work.",
    }
    unsafe_eval = evaluate_scenario(unsafe)
    assert unsafe_eval["status"] == "needs_hardening"
    assert unsafe_eval["certainty_flags"]
    hardened = harden_scenario(unsafe)
    hardened_eval = evaluate_scenario(hardened)
    assert hardened_eval["status"] == "ready_for_review"
    assert "not a prediction" in hardened["disclaimer"]
    assert hardened["decision_owner"] == "human"

    # Scenario evaluation must not mutate Maya state.
    for name, value in before.items():
        assert (ROOT / name).read_bytes() == value

    print(json.dumps({
        "status": "ok",
        "prototype_scenarios": 3,
        "unsafe_scenario_hardened": True,
        "single_path_recommendation_blocked": True,
        "state_unchanged": True,
    }))


if __name__ == "__main__":
    main()
