from __future__ import annotations

import json
import pickle
from pathlib import Path

from scipy import sparse

try:
    from .query_rag import rank_documents, retrieve_with_status
except ImportError:
    from query_rag import rank_documents, retrieve_with_status

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "rag_index_matrix.npz"
VECTORIZER_PATH = ROOT / "rag_vectorizer.pkl"
META_PATH = ROOT / "rag_index_meta.json"

QUERY_SYNONYMS = {
    "acid base": "acid base neutralisation neutralization titration ph",
    "acid-base": "acid base neutralisation neutralization titration ph",
    "ohm": "ohm resistance current voltage circuit resistor potential difference conductor wire meter bridge ammeter voltmeter",
    "ohm's": "ohm resistance current voltage circuit resistor potential difference conductor wire meter bridge ammeter voltmeter",
    "ohm law": "ohm law resistance current voltage circuit resistor potential difference conductor wire meter bridge ammeter voltmeter",
    "law of ohm": "ohm law resistance current voltage circuit resistor potential difference conductor wire meter bridge ammeter voltmeter",
    "resistance": "resistance resistor ohm circuit voltage current potential difference conductor wire meter bridge ammeter voltmeter",
    "potential difference": "potential difference resistance current voltage circuit resistor conductor wire meter bridge ammeter voltmeter",
    "voltage": "voltage circuit resistor current electrical potential conductor wire meter bridge ammeter voltmeter",
    "current": "current voltage resistance circuit conductor wire meter bridge ammeter voltmeter",
    "circuit": "circuit current voltage resistance conductor wire meter bridge ammeter voltmeter",
    "law of conservation": "conservation mass chemical reaction matter",
    "diffusion": "diffusion spread mixing solution particles",
    "titration": "titration neutralization acid base volume concentration",
    "reaction rate": "reaction rate temperature concentration catalyst kinetics",
    "ph": "ph acidity alkalinity indicator base acid",
}


def expand_query(query: str) -> str:
    lowered = query.lower()
    expanded = lowered
    for key, value in QUERY_SYNONYMS.items():
        if key in lowered:
            expanded = f"{expanded} {value}"
    return expanded


def load_data() -> tuple[pickle.Pickler, object, list[dict]]:
    with VECTORIZER_PATH.open("rb") as handle:
        vectorizer = pickle.load(handle)
    matrix = sparse.load_npz(str(INDEX_PATH))
    documents = json.loads(META_PATH.read_text(encoding="utf-8"))
    return vectorizer, matrix, documents


def search(query: str, vectorizer, matrix, documents, top_n: int = 5):
    return rank_documents(query, vectorizer, matrix, documents, top_n=top_n)


def main() -> None:
    if not INDEX_PATH.exists() or not VECTORIZER_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("RAG index files are missing. Run build_rag_index.py first.")

    vectorizer, matrix, documents = load_data()
    print("Science experiment RAG demo")
    print("Type 'q' or 'quit' to exit.\n")

    while True:
        query = input("Search: ").strip()
        if query.lower() in {"q", "quit", "exit"}:
            print("Goodbye.")
            break

        response = retrieve_with_status(query, vectorizer, matrix, documents)
        print(f"\nStatus: {response['status']}")
        print(response["message"])
        results = response["results"]
        if not results:
            continue

        for item in results:
            print(f"{item['score']:.4f} | {item['id']} | {item['title']} | {item['subject']} | class {item['class_level']} | {item['difficulty']} | source: {item['source_verification']} | video: {item['video_readiness']}")
            for citation in item.get("citations", []):
                if citation.get("passage_ids"):
                    print(f"  {citation['source_id']}: {', '.join(citation['passage_ids'])}")
        print()


if __name__ == "__main__":
    main()
