"""Build a lenient, non-destructive evidence review for the first catalog records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "chemistry_experiments.json"
SECTIONS_PATH = ROOT / "evidence" / "sections.json"
PASSAGES_PATH = ROOT / "evidence" / "passages.jsonl"
DEFAULT_OUTPUT = ROOT / "reports" / "first_10_evidence_review.json"


def load_passages() -> dict[str, dict[str, Any]]:
    if not PASSAGES_PATH.exists():
        return {}
    return {
        passage["passage_id"]: passage
        for passage in (
            json.loads(line)
            for line in PASSAGES_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def build_review(limit: int) -> dict[str, Any]:
    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))["experiments"][:limit]
    sections = {}
    if SECTIONS_PATH.exists():
        sections = {
            section["experiment_id"]: section
            for section in json.loads(SECTIONS_PATH.read_text(encoding="utf-8"))
        }
    passages = load_passages()
    reviews = []

    for position, record in enumerate(records, 1):
        section = sections.get(record["experiment_id"])
        passage_ids = section.get("passage_ids", []) if section else []
        evidence_previews = [
            {
                "passage_id": passage_id,
                "pdf_page": passages[passage_id].get("pdf_page"),
                "printed_page": passages[passage_id].get("printed_page"),
                "text_preview": " ".join(passages[passage_id].get("text", "").split())[:500],
            }
            for passage_id in passage_ids
            if passage_id in passages
        ]
        if evidence_previews:
            status = "candidate_manual_link_needs_human_confirmation"
            action = "Confirm title, page boundaries, procedure, quantities, and safety details against the manual."
        else:
            status = "no_local_manual_passage_candidate"
            action = "Find the exact official NCERT textbook/manual section and add page or passage evidence."

        reviews.append({
            "position": position,
            "experiment_id": record["experiment_id"],
            "title": record["title"],
            "subject": record["subject"],
            "class_level": record["class_level"],
            "difficulty": record["difficulty"],
            "summary": record["educational_goal"],
            "materials": record.get("materials", []),
            "procedure_summary": [
                {
                    "step_id": step["step_id"],
                    "instruction": step["instruction"],
                    "observation": step["observation"],
                }
                for step in record.get("procedure_steps", [])
            ],
            "existing_sources": record.get("sources", []),
            "candidate_section": {
                "section_id": section.get("section_id") if section else None,
                "manual_filename": section.get("manual_filename") if section else None,
                "printed_start": section.get("printed_start") if section else None,
                "printed_end": section.get("printed_end") if section else None,
                "passage_ids": passage_ids,
            },
            "evidence_previews": evidence_previews,
            "review_status": status,
            "recommended_action": action,
        })

    return {
        "review_policy": "Lenient candidate linking; no canonical records are modified and no candidate is treated as verified.",
        "record_count": len(reviews),
        "reviews": reviews,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Review the first catalog records against local evidence.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(build_review(args.limit), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Reviewed {args.limit} records against local evidence.")
    print(f"Saved candidate review to {output_path}")


if __name__ == "__main__":
    main()
