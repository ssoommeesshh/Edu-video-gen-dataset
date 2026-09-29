from __future__ import annotations

import json
import pickle
from pathlib import Path

from scipy import sparse

from query_rag import rank_documents

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "rag_index_matrix.npz"
VECTORIZER_PATH = ROOT / "rag_vectorizer.pkl"
META_PATH = ROOT / "rag_index_meta.json"

TEST_CASES = [
    ("acid-base titration", "chem_12_1002"),
    ("diffusion of ink in water", "chem_9_001"),
    ("reaction rate with temperature", "chem_12_902"),
    ("ohm law", "phy_12_001"),
]


def main() -> None:
    if not INDEX_PATH.exists() or not VECTORIZER_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("RAG index files are missing. Run build_rag_index.py first.")

    with VECTORIZER_PATH.open("rb") as handle:
        vectorizer = pickle.load(handle)

    matrix = sparse.load_npz(str(INDEX_PATH))
    documents = json.loads(META_PATH.read_text(encoding="utf-8"))

    print("RAG evaluation results\n")
    for query, expected_id in TEST_CASES:
        results = rank_documents(query, vectorizer, matrix, documents, top_n=5)
        result_ids = [item["id"] for item in results]
        top_hit = result_ids[0] if result_ids else None
        hit = expected_id in result_ids
        print(f"QUERY: {query}")
        print(f"EXPECTED: {expected_id}")
        print(f"TOP_HIT: {top_hit}")
        print(f"TOP_1_MATCHED: {top_hit == expected_id}")
        print(f"TOP_5_RECALL: {hit}")
        print(f"TOP_5: {result_ids}")
        print("-" * 60)


if __name__ == "__main__":
    main()
