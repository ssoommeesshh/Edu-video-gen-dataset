"""Evaluate retrieval ranking, filters, and abstention on the benchmark."""
from __future__ import annotations

import argparse
import json
import pickle
from collections import Counter
from pathlib import Path
from typing import Any

from scipy import sparse

from query_rag import rank_documents

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "data" / "retrieval_benchmark.json"
INDEX_PATH = ROOT / "rag_index_matrix.npz"
VECTORIZER_PATH = ROOT / "rag_vectorizer.pkl"
META_PATH = ROOT / "rag_index_meta.json"
DEFAULT_OUTPUT = ROOT / "reports" / "benchmark_evaluation.json"


def load_inputs() -> tuple[list[dict[str, Any]], Any, Any, list[dict[str, Any]]]:
    required = [BENCHMARK_PATH, INDEX_PATH, VECTORIZER_PATH, META_PATH]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Required benchmark or index files are missing: " + ", ".join(missing))

    cases = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))["cases"]
    with VECTORIZER_PATH.open("rb") as handle:
        vectorizer = pickle.load(handle)
    matrix = sparse.load_npz(str(INDEX_PATH))
    documents = json.loads(META_PATH.read_text(encoding="utf-8"))
    return cases, vectorizer, matrix, documents


def evaluate_case(
    case: dict[str, Any],
    vectorizer: Any,
    matrix: Any,
    documents: list[dict[str, Any]],
    *,
    min_score: float,
    min_margin: float,
) -> dict[str, Any]:
    results = rank_documents(
        case["query"],
        vectorizer,
        matrix,
        documents,
        top_n=5,
        subject=case.get("subject"),
        class_level=case.get("class_level"),
        min_score=min_score,
        min_margin=min_margin,
    )
    result_ids = [result["id"] for result in results]
    expected_id = case.get("expected_id")
    expected_outcome = case["expected_outcome"]
    supported = expected_outcome == "supported"
    top1_correct = bool(supported and result_ids and result_ids[0] == expected_id)
    recall_at_5 = bool(supported and expected_id in result_ids)
    should_abstain = not supported
    abstained = not result_ids
    passed = recall_at_5 if supported else abstained
    top_score = results[0]["score"] if results else 0.0
    second_score = results[1]["score"] if len(results) > 1 else 0.0

    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "category": case["category"],
        "split": case["split"],
        "expected_id": expected_id,
        "expected_outcome": expected_outcome,
        "filters": {key: case[key] for key in ("subject", "class_level") if key in case},
        "top1_id": result_ids[0] if result_ids else None,
        "result_ids": result_ids,
        "top_score": top_score,
        "score_margin": top_score - second_score if results else 0.0,
        "top1_correct": top1_correct,
        "recall_at_5": recall_at_5,
        "should_abstain": should_abstain,
        "abstained": abstained,
        "passed": passed,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    supported = [row for row in rows if row["expected_outcome"] == "supported"]
    rejection = [row for row in rows if row["expected_outcome"] != "supported"]

    def rate(items: list[dict[str, Any]], key: str) -> float | None:
        return round(sum(bool(item[key]) for item in items) / len(items), 4) if items else None

    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({row["category"] for row in rows}):
        group = [row for row in rows if row["category"] == category]
        by_category[category] = {
            "count": len(group),
            "pass_rate": rate(group, "passed"),
            "top1_accuracy": rate(group, "top1_correct"),
            "abstention_rate": rate(group, "abstained"),
        }

    by_split: dict[str, dict[str, Any]] = {}
    for split in sorted({row["split"] for row in rows}):
        group = [row for row in rows if row["split"] == split]
        by_split[split] = {
            "count": len(group),
            "pass_rate": rate(group, "passed"),
            "top1_accuracy": rate(group, "top1_correct"),
            "recall_at_5": rate(group, "recall_at_5"),
        }

    return {
        "case_count": len(rows),
        "category_counts": dict(Counter(row["category"] for row in rows)),
        "supported_count": len(supported),
        "rejection_count": len(rejection),
        "supported_top1_accuracy": rate(supported, "top1_correct"),
        "supported_recall_at_5": rate(supported, "recall_at_5"),
        "rejection_abstention_rate": rate(rejection, "abstained"),
        "overall_pass_rate": rate(rows, "passed"),
        "by_category": by_category,
        "by_split": by_split,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the retrieval benchmark.")
    parser.add_argument("--min-score", type=float, default=0.10)
    parser.add_argument("--min-margin", type=float, default=0.0)
    parser.add_argument("--split", choices=["all", "calibration", "holdout"], default="all")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.min_score < 0 or args.min_margin < 0:
        raise ValueError("Confidence thresholds cannot be negative.")

    cases, vectorizer, matrix, documents = load_inputs()
    if args.split != "all":
        cases = [case for case in cases if case["split"] == args.split]
    rows = [
        evaluate_case(
            case,
            vectorizer,
            matrix,
            documents,
            min_score=args.min_score,
            min_margin=args.min_margin,
        )
        for case in cases
    ]
    result = {
        "benchmark": str(BENCHMARK_PATH.relative_to(ROOT)),
        "min_score": args.min_score,
        "min_margin": args.min_margin,
        "summary": summarize(rows),
        "rows": rows,
    }
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = result["summary"]
    print(f"Evaluated {summary['case_count']} cases.")
    print(f"Supported top-1 accuracy: {summary['supported_top1_accuracy']}")
    print(f"Supported Recall@5: {summary['supported_recall_at_5']}")
    print(f"Non-supported abstention rate: {summary['rejection_abstention_rate']}")
    print(f"Overall benchmark pass rate: {summary['overall_pass_rate']}")
    print(f"Saved report to {output_path}")


if __name__ == "__main__":
    main()
