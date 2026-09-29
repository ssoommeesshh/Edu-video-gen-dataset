"""Validate the canonical dataset with no third-party dependencies."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "chemistry_experiments.json"
SECTIONS_PATH = ROOT / "evidence" / "sections.json"
PASSAGES_PATH = ROOT / "evidence" / "passages.jsonl"
REQUIRED = {
    "experiment_id", "subject", "class_level", "title", "difficulty",
    "educational_goal", "materials", "procedure_steps", "scenes",
    "sources", "image_assets", "status",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def main() -> None:
    try:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {DATA_PATH}: {exc}")

    records = payload.get("experiments") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        fail("top-level 'experiments' must be a non-empty array")

    ids: set[str] = set()
    sections = json.loads(SECTIONS_PATH.read_text(encoding="utf-8")) if SECTIONS_PATH.exists() else []
    section_by_id = {section["section_id"]: section for section in sections}
    passage_ids = {passage["passage_id"] for passage in (
        (json.loads(line) for line in PASSAGES_PATH.read_text(encoding="utf-8").splitlines())
        if PASSAGES_PATH.exists() else [])}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            fail(f"record {index} is not an object")
        missing = REQUIRED - record.keys()
        if missing:
            fail(f"record {index} is missing: {', '.join(sorted(missing))}")
        experiment_id = record["experiment_id"]
        if experiment_id in ids:
            fail(f"duplicate experiment_id: {experiment_id}")
        ids.add(experiment_id)
        if record["subject"] not in {"Chemistry", "Physics"}:
            fail(f"{experiment_id}: subject must be Chemistry or Physics")
        if record["class_level"] not in {8, 9, 10, 11, 12}:
            fail(f"{experiment_id}: class_level must be 8-12")
        if len(record["procedure_steps"]) < 3:
            fail(f"{experiment_id}: add at least three procedure steps")
        if len(record["scenes"]) < 1:
            fail(f"{experiment_id}: add at least one scene")
        if len(record["sources"]) < 1:
            fail(f"{experiment_id}: add at least one source")
        for scene in record["scenes"]:
            if scene["image_asset_id"] not in {asset["image_asset_id"] for asset in record["image_assets"]}:
                fail(f"{experiment_id}: scene references unknown image asset")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict):
            fail(f"{experiment_id}: missing evidence review state")
        for section_id in evidence.get("section_ids", []):
            if section_id not in section_by_id or section_by_id[section_id]["experiment_id"] != experiment_id:
                fail(f"{experiment_id}: unknown or mismatched evidence section {section_id}")
        scene_ids = {scene["scene_id"] for scene in record["scenes"]}
        for step in record["procedure_steps"]:
            unknown = set(step.get("scene_ids", [])) - scene_ids
            if unknown:
                fail(f"{experiment_id}: step {step['step_id']} links unknown scenes {sorted(unknown)}")
            if step.get("scene_link_status") == "verified" and not step.get("scene_ids"):
                fail(f"{experiment_id}: step {step['step_id']} is scene-verified without a scene link")
        claim_ids = [claim["claim_id"] for claim in evidence.get("claims", [])]
        if len(claim_ids) != len(set(claim_ids)):
            fail(f"{experiment_id}: evidence claim IDs must be unique")
        if evidence.get("source_verification") == "verified" and not all(claim.get("review_status") == "verified" for claim in evidence.get("claims", [])):
            fail(f"{experiment_id}: source marked verified while claims remain unverified")
        if evidence.get("source_verification") == "no_link_in_supplied_pdfs" and evidence.get("section_ids"):
            fail(f"{experiment_id}: no-link status conflicts with a linked manual section")
        if evidence.get("retrieval_eligibility") == "eligible" and evidence.get("source_verification") != "verified":
            fail(f"{experiment_id}: retrieval-eligible record lacks complete source verification")
        if evidence.get("video_readiness") == "ready" and (
            evidence.get("retrieval_eligibility") != "eligible"
            or any(step.get("scene_link_status") != "verified" or not step.get("scene_ids") for step in record["procedure_steps"])
        ):
            fail(f"{experiment_id}: video-ready record has incomplete evidence or scene links")
        for source in record["sources"]:
            if set(source.get("passage_ids", [])) - passage_ids:
                fail(f"{experiment_id}: source {source['source_id']} references an unknown passage")
        if passage_ids:
            for claim in evidence.get("claims", []):
                if set(claim.get("passage_ids", [])) - passage_ids:
                    fail(f"{experiment_id}: claim {claim['claim_id']} references an unknown passage")

    classes = sorted({record["class_level"] for record in records})
    print(f"Validated {len(records)} records across Classes {', '.join(map(str, classes))}.")
    print("All experiment IDs are unique; scene, section, and claim links are structurally checked.")


if __name__ == "__main__":
    main()
