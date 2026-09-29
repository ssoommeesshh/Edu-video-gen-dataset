"""Retrieve experiments and build source-grounded video prompt bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from pathlib import Path
from typing import Any

from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

try:
    from .query_rag import retrieve_with_status
except ImportError:
    from query_rag import retrieve_with_status

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "chemistry_experiments.json"
INDEX_PATH = ROOT / "rag_index_matrix.npz"
VECTORIZER_PATH = ROOT / "rag_vectorizer.pkl"
META_PATH = ROOT / "rag_index_meta.json"
GRAPH_PATH = ROOT / "evidence" / "evidence_graph.json"
DEFAULT_OUTPUT = ROOT / "exports" / "rag_prompt_bundle.json"


def load_canonical_records() -> dict[str, dict[str, Any]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {record["experiment_id"]: record for record in payload["experiments"]}


def load_index() -> tuple[Any, Any, list[dict[str, Any]]]:
    required = [INDEX_PATH, VECTORIZER_PATH, META_PATH]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "RAG index files not found. Run scripts\\build_rag_index.py first: "
            + ", ".join(missing)
        )

    with VECTORIZER_PATH.open("rb") as handle:
        vectorizer = pickle.load(handle)
    matrix = sparse.load_npz(str(INDEX_PATH))
    documents = json.loads(META_PATH.read_text(encoding="utf-8"))
    return vectorizer, matrix, documents


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def make_step_prompt(record: dict[str, Any], scene: dict[str, Any], step: dict[str, Any]) -> str:
    materials = ", ".join(record.get("materials", []))
    visible_actions = ", ".join(scene.get("visible_actions", []))
    safety_notes = "; ".join(record.get("safety_notes", []))
    return (
        f"Create a realistic educational science video clip for Class {record['class_level']} "
        f"{record['subject']} experiment '{record['title']}'. "
        f"Show the scene '{scene['name']}': {scene['description']} "
        f"Perform this step: {step['instruction']} "
        f"Show the expected observation: {step['observation']} "
        f"Visible actions may include: {visible_actions}. "
        f"Use only these materials: {materials}. "
        f"Follow these reviewed safety notes: {safety_notes}. "
        "Keep the apparatus, quantities, actions, and scientific outcome accurate. "
        "Use clear classroom lighting, stable framing, natural motion, and no labels or watermark."
    )


def evidence_review(record: dict[str, Any]) -> dict[str, Any]:
    """Require reviewed claim support and reviewed step-to-scene links before prompting."""
    if not GRAPH_PATH.exists():
        return {"status": "review_required", "missing_claims": ["evidence graph not built"], "citations": []}
    try:
        from .build_evidence_graph import GRAPH_VERSION
    except ImportError:
        from build_evidence_graph import GRAPH_VERSION
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    fingerprint_inputs = ["data/chemistry_experiments.json", "evidence/manuals.json", "evidence/sections.json",
                          "evidence/passages.jsonl", "evidence/reviews.json"]
    fingerprint = hashlib.sha256((str(GRAPH_VERSION) + "".join(hashlib.sha256((ROOT / path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        for path in fingerprint_inputs)).encode()).hexdigest()
    if graph.get("build_fingerprint") != fingerprint:
        return {"status": "review_required", "missing_claims": ["evidence graph is stale; rebuild it"], "citations": []}
    claims = [node for node in graph["nodes"] if node.get("type") == "claim" and node.get("experiment_id") == record["experiment_id"]]
    edges = graph["edges"]
    required_ids = {claim["id"] for claim in claims}
    claim_by_id = {claim["id"]: claim for claim in claims}
    claim_by_path = {claim.get("field_path"): claim["id"] for claim in claims}
    missing = []
    citations = []
    claim_citations = {}
    path_citations = {}
    for claim_id in sorted(required_ids):
        supported = [edge for edge in edges if edge.get("from") == claim_id and edge.get("type") == "SUPPORTED_BY" and edge.get("status") == "verified"]
        claim_citations[claim_id] = [edge["to"] for edge in supported]
        claim = claim_by_id[claim_id]
        path = claim.get("field_path", "")
        path_citations[path] = sorted(set(path_citations.get(path, []) + claim_citations[claim_id]))
        if not supported:
            candidates = [edge for edge in edges if edge.get("from") == claim_id and edge.get("type") == "CANDIDATE_SUPPORT"]
            missing.append({"claim_id": claim_id, "claim": claim.get("text"), "candidate_passage_ids": [edge["to"] for edge in candidates]})
        citations.extend(edge["to"] for edge in supported)
    for step_index, step in enumerate(record["procedure_steps"]):
        if step.get("scene_link_status") != "verified" or not step.get("scene_ids"):
            missing.append({"step_id": step["step_id"], "claim": "step-to-scene relationship", "candidate_scene_ids": step.get("scene_ids", [])})
        for field in ("instruction", "observation"):
            claim_id = claim_by_path.get(f"/procedure_steps/{step_index}/{field}")
            if claim_id:
                claim_citations[f"step:{step['step_id']}:{field}"] = claim_citations.get(claim_id, [])
    return {"status": "ready" if not missing else "review_required", "missing_claims": missing,
            "citations": sorted(set(citations)), "claim_citations": claim_citations,
            "path_citations": path_citations}


def build_bundle(query: str, top_k: int, experiment_id: str | None = None) -> dict[str, Any]:
    records = load_canonical_records()
    if experiment_id is not None:
        if experiment_id not in records:
            raise ValueError(f"Unknown experiment_id: {experiment_id}")
        retrieval_status = {
            "status": "explicit_selection",
            "message": f"Using explicitly selected experiment {experiment_id}.",
            "results": [{"id": experiment_id, "score": None}],
        }
    else:
        vectorizer, matrix, documents = load_index()
        retrieval_status = retrieve_with_status(query, vectorizer, matrix, documents, top_n=max(top_k, 2))

    if retrieval_status["status"] not in {"confident_match", "explicit_selection"}:
        return {
            "query": query,
            "status": retrieval_status["status"],
            "message": retrieval_status["message"],
            "suggestions": retrieval_status["results"],
            "retrieved_experiments": [],
            "prompt_inputs": [],
        }

    ranked = retrieval_status["results"][:1]
    if len(ranked) != 1:
        return {"query": query, "status": "review_required", "message": "Select exactly one experiment before planning prompts.",
                "retrieved_experiments": [], "prompt_inputs": [], "review_report": {"required": ["explicit single experiment selection"]}}
    selected_record = records[ranked[0]["id"]]
    review = evidence_review(selected_record)
    if review["status"] != "ready":
        return {"query": query, "status": "review_required",
                "message": "Required claims or step-to-scene links lack verified evidence; no prompts were generated.",
                "retrieved_experiments": [{"experiment_id": selected_record["experiment_id"], "title": selected_record["title"]}],
                "prompt_inputs": [], "review_report": review}
    experiments: list[dict[str, Any]] = []
    prompt_inputs: list[dict[str, Any]] = []

    for result in ranked:
        experiment_id = result["id"]
        record = records.get(experiment_id)
        if record is None:
            continue

        scenes = record.get("scenes", [])
        procedure_steps = record.get("procedure_steps", [])
        scene_steps: list[dict[str, Any]] = []
        scenes_by_id = {scene["scene_id"]: scene for scene in scenes}
        for procedure_index, step in enumerate(procedure_steps):
            for scene_id in step["scene_ids"]:
                scene = scenes_by_id[scene_id]
                image_asset = next(
                    (asset for asset in record.get("image_assets", [])
                     if asset.get("image_asset_id") == scene.get("image_asset_id")),
                    None,
                )
                if image_asset is None:
                    image_asset = next(
                        (asset for asset in record.get("image_assets", []) if asset.get("role") == "starting_image"),
                        {},
                    )
                prompt_input = {
                    "experiment_id": experiment_id,
                    "scene_id": scene["scene_id"],
                    "step_id": step["step_id"],
                    "prompt": make_step_prompt(record, scene, step),
                    "negative_prompt": "blurry, distorted apparatus, incorrect measurements, text artifacts, watermark",
                    "starting_image": image_asset.get("url", ""),
                    "source_ids": [source["source_id"] for source in record.get("sources", [])],
                }
                citation_paths = [f"/procedure_steps/{procedure_index}/instruction",
                    f"/procedure_steps/{procedure_index}/observation"]
                citation_paths += [f"/materials/{i}" for i in range(len(record.get("materials", [])))]
                citation_paths += [f"/safety_notes/{i}" for i in range(len(record.get("safety_notes", [])))]
                scene_index = scenes.index(scene)
                citation_paths.append(f"/scenes/{scene_index}/description")
                citation_paths += [f"/scenes/{scene_index}/visible_actions/{i}" for i in range(len(scene.get("visible_actions", [])))]
                prompt_input["passage_ids"] = sorted({pid for path in citation_paths for pid in review["path_citations"].get(path, [])})
                scene_steps.append(prompt_input)
                prompt_inputs.append(prompt_input)

        if not procedure_steps:
            for scene in scenes:
                step = {
                    "step_id": f"{scene['scene_id']}_overview",
                    "instruction": scene["description"],
                    "observation": "; ".join(scene.get("visible_actions", [])),
                }
                prompt_input = {
                    "experiment_id": experiment_id,
                    "scene_id": scene["scene_id"],
                    "step_id": step["step_id"],
                    "prompt": make_step_prompt(record, scene, step),
                    "negative_prompt": "blurry, distorted apparatus, text artifacts, watermark",
                    "starting_image": "",
                    "source_ids": [source["source_id"] for source in record.get("sources", [])],
                }
                scene_steps.append(prompt_input)
                prompt_inputs.append(prompt_input)

        scene_bundle = [{
            "scene_id": scene["scene_id"],
            "scene_name": scene["name"],
            "description": scene["description"],
        } for scene in scenes]

        experiments.append({
            "experiment_id": experiment_id,
            "retrieval_score": result.get("score"),
            "title": record["title"],
            "subject": record["subject"],
            "class_level": record["class_level"],
            "difficulty": record["difficulty"],
            "educational_goal": record["educational_goal"],
            "status": record.get("status"),
            "source_ids": [source["source_id"] for source in record.get("sources", [])],
            "passage_ids": review["citations"],
            "scenes": scene_bundle,
        })

    return {
        "query": query,
        "status": retrieval_status["status"],
        "message": retrieval_status["message"],
        "top_k": top_k,
        "retrieved_experiments": experiments,
        "prompt_inputs": prompt_inputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve NCERT experiments and create grounded video prompts."
    )
    parser.add_argument("query", help="Natural-language experiment query.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of experiments to retrieve.")
    parser.add_argument("--experiment-id", default=None, help="Explicit catalog ID selected from suggestions.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON bundle output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1")

    bundle = build_bundle(args.query, args.top_k, args.experiment_id)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Status: {bundle['status']}")
    print(bundle["message"])
    for suggestion in bundle.get("suggestions", []):
        print(
            f"- {suggestion['id']} | {suggestion['title']} | "
            f"{suggestion['subject']} | class {suggestion['class_level']} | "
            f"score {suggestion['score']:.4f}"
        )
    print(f"Retrieved {len(bundle['retrieved_experiments'])} experiments.")
    print(f"Built {len(bundle['prompt_inputs'])} scene-step prompts.")
    print(f"Saved prompt bundle to {output_path}")


if __name__ == "__main__":
    main()
