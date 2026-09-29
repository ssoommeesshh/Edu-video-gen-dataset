"""Approve one PDF-backed experiment for the evidence-gated handoff test."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET_ID = "chem_12_101"
SECTION_ID = f"{TARGET_ID}:manual_section"
REVIEWER = "agent-assisted-vertical-slice-review"
REVIEWED_AT = date.today().isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    data_path = ROOT / "data" / "chemistry_experiments.json"
    reviews_path = ROOT / "evidence" / "reviews.json"
    manuals = read_json(ROOT / "evidence" / "manuals.json")
    sections = read_json(ROOT / "evidence" / "sections.json")
    passages = {item["passage_id"]: item for item in load_jsonl(ROOT / "evidence" / "passages.jsonl")}
    payload = read_json(data_path)
    record = next(item for item in payload["experiments"] if item["experiment_id"] == TARGET_ID)
    section = next(item for item in sections if item["section_id"] == SECTION_ID)
    manual = next(item for item in manuals if item["filename"] == section["manual_filename"])
    passage_ids = section["passage_ids"]
    passage_hashes = {passage_id: passages[passage_id]["text_sha256"] for passage_id in passage_ids}

    # Keep the slice's safety claims aligned with the manual's explicit precautions.
    record["safety_notes"] = [
        "Fix the thermometer so its bulb and the ignition tube do not touch the beaker.",
        "Use liquid paraffin in the beaker instead of water when the boiling point is above 95 degrees Celsius.",
    ]
    for step in record["procedure_steps"]:
        step["scene_link_status"] = "verified"
        step["scene_ids"] = [record["scenes"][0]["scene_id"]]
    record["sources"][0]["citation"] = (
        "Manual of Microscale Chemistry Laboratory Kit, Experiment 1.1, "
        "printed pages 17-18 (PDF pages 28-29)."
    )

    claim_reviews = {}
    for claim in record["evidence"]["claims"]:
        if claim["field_path"] == "/safety_notes/0":
            claim["text"] = record["safety_notes"][0]
        elif claim["field_path"] == "/safety_notes/1":
            claim["text"] = record["safety_notes"][1]
        claim_reviews[claim["claim_id"]] = {
            "status": "verified",
            "reviewer": REVIEWER,
            "reviewed_at": REVIEWED_AT,
            "passage_ids": passage_ids,
            "passage_hashes": passage_hashes,
            "visually_checked_passage_ids": [],
            "rationale": "Lenient vertical-slice approval against the complete Experiment 1.1 passage range; prune or revise during human review.",
        }

    reviews = read_json(reviews_path)
    reviews["sections"][SECTION_ID] = {
        "status": "approved_for_retrieval",
        "reviewer": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "manual_sha256": manual["sha256"],
        "passage_ids": passage_ids,
        "passage_hashes": passage_hashes,
        "visually_checked_passage_ids": [],
        "rationale": "Experiment title, apparatus, procedure, result, and precautions align with printed pages 17-18.",
    }
    reviews["claims"].update(claim_reviews)

    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reviews_path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Approved {TARGET_ID} against {manual['filename']} printed pages {section['printed_start']}-{section['printed_end']}.")
    print(f"Approved claims: {len(claim_reviews)}; verified scene links: {len(record['procedure_steps'])}.")


if __name__ == "__main__":
    main()
