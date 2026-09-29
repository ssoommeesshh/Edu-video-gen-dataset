from __future__ import annotations

import json
import pickle
from pathlib import Path

from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

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


def rank_documents(
    query: str,
    vectorizer,
    matrix,
    documents,
    top_n: int = 5,
    subject: str | None = None,
    class_level: int | str | None = None,
    min_score: float = 0.0,
    min_margin: float = 0.0,
):
    search_query = expand_query(query)
    qv = vectorizer.transform([search_query])
    scores = cosine_similarity(qv, matrix).flatten()
    eligible = []
    for index, document in enumerate(documents):
        metadata = document["metadata"]
        if subject is not None and str(metadata.get("subject", "")).casefold() != str(subject).casefold():
            continue
        if class_level is not None and str(metadata.get("class_level", "")) != str(class_level):
            continue
        eligible.append(index)

    ranked_indexes = sorted(eligible, key=lambda index: scores[index], reverse=True)
    if not ranked_indexes:
        return []
    if scores[ranked_indexes[0]] < min_score:
        return []
    if len(ranked_indexes) > 1 and scores[ranked_indexes[0]] - scores[ranked_indexes[1]] < min_margin:
        return []

    idxs = ranked_indexes[:top_n]
    ranked = []
    for idx in idxs:
        doc = documents[int(idx)]
        meta = doc["metadata"]
        ranked.append({
            "score": float(scores[idx]),
            "id": doc["id"],
            "title": meta.get("title"),
            "subject": meta.get("subject"),
            "class_level": meta.get("class_level"),
            "difficulty": meta.get("difficulty"),
            "source_verification": meta.get("source_verification", "unverified"),
            "retrieval_eligibility": meta.get("retrieval_eligibility", "review_required"),
            "video_readiness": meta.get("video_readiness", "review_required"),
            "citations": meta.get("citations", []),
        })
    return ranked


def retrieve_with_status(
    query: str,
    vectorizer,
    matrix,
    documents,
    top_n: int = 5,
    subject: str | None = None,
    class_level: int | str | None = None,
    confident_score: float = 0.30,
    confident_margin: float = 0.05,
):
    """Return a confident match or safe in-catalog alternatives.

    Retrieval never claims a weak result is the requested experiment. Borderline
    results require the user to select an in-scope option explicitly.
    """
    candidates = rank_documents(
        query,
        vectorizer,
        matrix,
        documents,
        top_n=top_n,
        subject=subject,
        class_level=class_level,
    )
    if not candidates or candidates[0]["score"] < confident_score:
        return {
            "status": "out_of_scope",
            "message": (
                "I could not find a strong match in the NCERT experiment catalog. "
                "This may be outside the supported domain. Here are the closest "
                "in-catalog options, if any; please choose one to continue."
            ),
            "results": candidates,
        }

    margin = candidates[0]["score"] - candidates[1]["score"] if len(candidates) > 1 else candidates[0]["score"]
    if margin < confident_margin:
        return {
            "status": "selection_required",
            "message": (
                "I found several nearby NCERT experiments but not one unambiguous "
                "match. Please choose one of these in-catalog options to continue."
            ),
            "results": candidates,
        }

    return {
        "status": "confident_match",
        "message": "I found a confident match in the NCERT experiment catalog.",
        "results": candidates,
    }


def main() -> None:
    if not INDEX_PATH.exists() or not META_PATH.exists() or not VECTORIZER_PATH.exists():
        raise FileNotFoundError(
            "Index files not found. Run build_rag_index.py first."
        )

    with VECTORIZER_PATH.open("rb") as handle:
        vectorizer = pickle.load(handle)

    matrix = sparse.load_npz(str(INDEX_PATH))
    documents = json.loads(META_PATH.read_text(encoding="utf-8"))

    while True:
        query = input("\nEnter a search query (or 'q' to quit): ").strip()
        if query.lower() in {"q", "quit", "exit"}:
            print("Exiting RAG search.")
            break

        response = retrieve_with_status(query, vectorizer, matrix, documents)
        print(f"\nStatus: {response['status']}")
        print(response["message"])
        for item in response["results"]:
            print(f"Score: {item['score']:.4f}")
            print(f"ID: {item['id']}")
            print(f"Title: {item['title']}")
            print(f"Subject: {item['subject']}")
            print(f"Class: {item['class_level']}")
            print("-" * 60)


if __name__ == "__main__":
    main()
