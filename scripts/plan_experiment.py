"""Export a provider-independent clip plan; query-only requests never execute."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

try:
    from .build_rag_prompt_bundle import ROOT, build_bundle, load_canonical_records, load_index
    from .query_rag import retrieve_with_status
except ImportError:
    from build_rag_prompt_bundle import ROOT, build_bundle, load_canonical_records, load_index
    from query_rag import retrieve_with_status


def revision():
    files = ["data/chemistry_experiments.json", "evidence/evidence_graph.json"]
    hashes = {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for name in files}
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return {"git_commit": result.stdout.strip() if result.returncode == 0 else None,
            "content_hashes": hashes}


def plan_experiment(query="", experiment_id=None, durations=None):
    """Require explicit selection and existing evidence approval. Durations are provisional."""
    if not experiment_id:
        vectorizer, matrix, documents = load_index()
        decision = retrieve_with_status(query, vectorizer, matrix, documents)
        return {"status": "out_of_scope" if decision["status"] == "out_of_scope" else "selection_required",
                "query": query, "message": "Select a catalog experiment ID before planning.",
                "candidates": decision["results"], "clips": []}
    records = load_canonical_records()
    if experiment_id not in records:
        return {"status": "not_in_catalog", "experiment_id": experiment_id, "clips": []}
    record = records[experiment_id]
    bundle = build_bundle(query or record["title"], top_k=1, experiment_id=experiment_id)
    if not bundle.get("prompt_inputs"):
        return {"status": "blocked", "experiment_id": experiment_id, "clips": [],
                "message": bundle.get("message"), "review_report": bundle.get("review_report", {})}
    durations = durations or {}
    scenes = {s["scene_id"]: s for s in record["scenes"]}
    steps = {s["step_id"]: s for s in record["procedure_steps"]}
    clips = []
    previous_scene = None
    for prompt in bundle["prompt_inputs"]:
        scene_id, step_id = prompt["scene_id"], prompt["step_id"]
        clip_id = f"{scene_id}_step_{step_id}"
        duration = float(durations.get(clip_id, 1.0))
        if not math.isfinite(duration) or not 0 < duration <= 60:
            raise ValueError(f"Invalid duration for {clip_id}: expected 0 < seconds <= 60")
        clips.append({
            "clip_id": clip_id, "scene_id": scene_id, "step_ids": [step_id],
            "new_scene": scene_id != previous_scene,
            "image_prompt": scenes[scene_id]["description"], "motion_prompt": prompt["prompt"],
            "negative_prompt": prompt["negative_prompt"], "stop_condition": steps[step_id]["observation"],
            "duration_seconds": duration, "duration_status": "user_specified" if clip_id in durations else "provisional_cpu_test",
            "starting_image": None, "source_passage_ids": prompt["passage_ids"],
            "review_status": "evidence_gate_passed", "visual_review_status": "not_reviewed",
        })
        previous_scene = scene_id
    unknown = set(durations) - {c["clip_id"] for c in clips}
    if unknown:
        raise ValueError(f"Duration overrides contain unknown clip IDs: {sorted(unknown)}")
    reviews = json.loads((ROOT / "evidence/reviews.json").read_text(encoding="utf-8"))["claims"]
    used_reviews = [reviews[c["claim_id"]] for c in record["evidence"]["claims"]]
    provenance = {
        "reviewers": sorted({r["reviewer"] for r in used_reviews}),
        "review_kinds": sorted({r.get("review_kind", "unspecified") for r in used_reviews}),
        "human_review_status": "approved" if all(r.get("human_review_status") == "approved" for r in used_reviews) else "pending",
    }
    return {"contract_version": "1.0", "status": "ready", "experiment_id": experiment_id,
            "title": record["title"], "subject": record["subject"], "dataset_revision": revision(),
            "source_references": record.get("sources", []), "review_status": "evidence_gate_passed",
            "visual_review_status": "not_reviewed", "review_provenance": provenance, "clips": clips}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="")
    parser.add_argument("--experiment-id")
    parser.add_argument("--durations", help="JSON mapping stable clip IDs to seconds")
    parser.add_argument("--output", help="Otherwise emit JSON to stdout")
    args = parser.parse_args()
    if not args.query and not args.experiment_id:
        parser.error("provide --query or --experiment-id")
    durations = json.loads(Path(args.durations).read_text(encoding="utf-8")) if args.durations else None
    result = plan_experiment(args.query, args.experiment_id, durations)
    if result["status"] == "ready":
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schema/clip_plan.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(result)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        # ASCII JSON keeps redirected stdout portable on Windows; files remain UTF-8.
        print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
