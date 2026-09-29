import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_evidence_graph as graph


def inputs():
    record = next(r for r in graph.read_json(ROOT / 'data/chemistry_experiments.json')['experiments']
                  if r['experiment_id'] == 'chem_12_101')
    reviews = graph.read_json(ROOT / 'evidence/reviews.json')
    passages = {p['passage_id']: p for p in graph.load_jsonl(ROOT / 'evidence/passages.jsonl')}
    claim = next(c for c in record['evidence']['claims'] if c['field_path'] == '/procedure_steps/1/instruction')
    return record, claim, reviews, passages


def test_review_binds_exact_claim_and_live_field():
    record, claim, reviews, passages = inputs()
    review = reviews['claims'][claim['claim_id']]
    assert graph.valid_claim_review(review, claim, record, passages)
    stale = copy.deepcopy(record)
    stale['procedure_steps'][1]['instruction'] = 'Heat rapidly instead.'
    assert not graph.valid_claim_review(review, claim, stale, passages)
    changed = dict(claim, text=stale['procedure_steps'][1]['instruction'])
    assert not graph.valid_claim_review(review, changed, stale, passages)
    no_binding = {k: v for k, v in review.items() if k != 'claim_sha256'}
    assert not graph.valid_claim_review(no_binding, claim, record, passages)
    wrong_quote = copy.deepcopy(review)
    wrong_quote['quotes'][0]['exact_quote'] = 'Invented passage text.'
    assert not graph.valid_claim_review(wrong_quote, claim, record, passages)


def test_graph_support_is_exactly_reviewed_pages():
    _, _, reviews, _ = inputs()
    built = graph.build_graph()
    for cid, review in reviews['claims'].items():
        if not cid.startswith('chem_12_101:'):
            continue
        actual = {e['to'] for e in built['edges'] if e['from'] == cid and e['type'] == 'SUPPORTED_BY'}
        assert actual == set(review['passage_ids']), cid


def test_evidence_query_uses_current_fingerprint():
    from scripts.query_evidence_graph import search
    result = search('Determine the boiling point of an organic compound', top_n=1, experiment_id='chem_12_101')
    assert result['matches'][0]['experiment_id'] == 'chem_12_101'
    assert result['matches'][0]['confidence_status'] == 'source_verified'
    assert result['retrieval_status'] == 'explicit_selection'
    assert all(c['human_review_status'] == 'pending' for c in result['matches'][0]['claims'])


def test_explicit_review_does_not_depend_on_lexical_overlap(monkeypatch):
    record, claim, reviews, passages = inputs()
    # A deliberately lexically different paraphrase, confined to this test fixture.
    claim['text'] = 'Thermally energise container.'
    record['procedure_steps'][1]['instruction'] = claim['text']
    review = reviews['claims'][claim['claim_id']]
    binding = {k: claim[k] for k in ['field_path', 'text', 'kind']}
    review['claim_sha256'] = hashlib.sha256(json.dumps(binding, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert all(graph.overlap(claim['text'], passages[pid]['text']) < 0.12 for pid in review['passage_ids'])
    original = graph.read_json
    def read(path):
        if path.name == 'chemistry_experiments.json':
            return {'experiments': [record]}
        if path.name == 'reviews.json':
            return reviews
        return original(path)
    monkeypatch.setattr(graph, 'read_json', read)
    built = graph.build_graph()
    actual = {e['to'] for e in built['edges'] if e['from'] == claim['claim_id'] and e['type'] == 'SUPPORTED_BY'}
    assert actual == set(review['passage_ids'])
