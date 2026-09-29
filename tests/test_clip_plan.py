import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.plan_experiment import plan_experiment


def test_ready_plan_has_stable_ids_and_sources():
    plan = plan_experiment(experiment_id="chem_12_101")
    Draft202012Validator(json.loads((ROOT / "schema/clip_plan.schema.json").read_text())).validate(plan)
    assert plan["experiment_id"] == "chem_12_101"
    assert [c["step_ids"] for c in plan["clips"]] == [[1], [2], [3]]
    assert [c["new_scene"] for c in plan["clips"]] == [True, False, False]
    assert all(c["source_passage_ids"] for c in plan["clips"])
    assert plan["visual_review_status"] == "not_reviewed"
    assert plan["review_provenance"]["review_kinds"] == ["agent_visual_source_review"]
    assert plan["review_provenance"]["human_review_status"] == "pending"
    clip_id = plan["clips"][0]["clip_id"]
    overridden = plan_experiment(experiment_id="chem_12_101", durations={clip_id: 0.5})
    assert overridden["clips"][0]["duration_seconds"] == 0.5
    with pytest.raises(ValueError):
        plan_experiment(experiment_id="chem_12_101", durations={"typo": 1})


@pytest.mark.parametrize("experiment_id,status", [("chem_9_001", "blocked"), ("does_not_exist", "not_in_catalog")])
def test_unavailable_record_has_no_clips(experiment_id, status):
    plan = plan_experiment(experiment_id=experiment_id)
    assert plan["status"] == status
    assert plan["clips"] == []


@pytest.mark.parametrize("query", ["boiling point organic compound", "zzzxxyy spaceship banking mortgage"])
def test_query_never_silently_selects(query):
    decision = plan_experiment(query=query)
    assert decision["status"] in {"selection_required", "out_of_scope"}
    assert decision["clips"] == []


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_evidence_gate_survives_checkout_line_endings(tmp_path, monkeypatch, newline):
    from scripts import build_rag_prompt_bundle as bundle
    names = ["data/chemistry_experiments.json", "evidence/manuals.json", "evidence/sections.json",
             "evidence/passages.jsonl", "evidence/reviews.json", "evidence/evidence_graph.json"]
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT / name).read_text(encoding="utf-8")
        target.write_bytes(text.replace("\n", newline).encode("utf-8"))
    monkeypatch.setattr(bundle, "ROOT", tmp_path)
    monkeypatch.setattr(bundle, "GRAPH_PATH", tmp_path / "evidence/evidence_graph.json")
    record = bundle.load_canonical_records()["chem_12_101"]
    assert bundle.evidence_review(record)["status"] == "ready"
    with (tmp_path / "evidence/reviews.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    assert bundle.evidence_review(record)["status"] == "review_required"
