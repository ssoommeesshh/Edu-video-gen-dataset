"""Build JSONL files for RAG and downstream prompt generation."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "chemistry_experiments.json"
EXPORT_DIR = ROOT / "exports"


def record_to_text(record: dict) -> str:
    steps = "\n".join(
        f"{step['step_id']}. {step['instruction']} Observation: {step['observation']}"
        for step in record["procedure_steps"]
    )
    scenes = "\n".join(
        f"{scene['name']}: {scene['description']} Actions: {', '.join(scene['visible_actions'])}"
        for scene in record["scenes"]
    )
    return "\n".join([
        f"Experiment: {record['title']}",
        f"Class: {record['class_level']}",
        f"Subject: {record['subject']}",
        f"Chapter: {record.get('chapter', '')}",
        f"Goal: {record['educational_goal']}",
        f"Concepts: {', '.join(record.get('concepts', []))}",
        f"Materials: {', '.join(record['materials'])}",
        "Procedure:\n" + steps,
        "Visual scenes:\n" + scenes,
        f"Tags: {', '.join(record.get('tags', []))}",
    ])


def main() -> None:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records = payload["experiments"]
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    with (EXPORT_DIR / "chemistry_experiments.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    with (EXPORT_DIR / "rag_documents.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            document = {
                "id": record["experiment_id"],
                "text": record_to_text(record),
                "metadata": {
                    "subject": record["subject"],
                    "class_level": record["class_level"],
                    "title": record["title"],
                    "difficulty": record["difficulty"],
                    "tags": record.get("tags", []),
                    "source_ids": [source["source_id"] for source in record["sources"]],
                    "source_verification": record.get("evidence", {}).get("source_verification", "unverified"),
                    "retrieval_eligibility": record.get("evidence", {}).get("retrieval_eligibility", "review_required"),
                    "video_readiness": record.get("evidence", {}).get("video_readiness", "review_required"),
                    "section_ids": record.get("evidence", {}).get("section_ids", []),
                    "citations": [
                        {"source_id": source["source_id"], "passage_ids": source.get("passage_ids", []),
                         "verification_status": source.get("verification_status")}
                        for source in record["sources"]
                    ],
                },
            }
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")

    with (EXPORT_DIR / "prompt_inputs.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            prompt_input = {
                "experiment_id": record["experiment_id"],
                "input": record_to_text(record),
                "scene_count": len(record["scenes"]),
                "image_assets": record["image_assets"],
                "evidence_status": record.get("evidence", {}),
            }
            handle.write(json.dumps(prompt_input, ensure_ascii=False) + "\n")

    print(f"Built three JSONL exports for {len(records)} experiments in {EXPORT_DIR}.")


if __name__ == "__main__":
    main()
