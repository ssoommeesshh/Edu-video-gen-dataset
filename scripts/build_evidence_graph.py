"""Build a deterministic, review-gated JSON evidence graph from local data."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GRAPH_VERSION = 4


def evidence_fingerprint(root):
    """One newline-stable fingerprint shared by graph builders and consumers."""
    names = ['data/chemistry_experiments.json', 'evidence/manuals.json', 'evidence/sections.json',
             'evidence/passages.jsonl', 'evidence/reviews.json']
    hashes = ''.join(hashlib.sha256((root / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
                     for name in names)
    return hashlib.sha256((str(GRAPH_VERSION) + hashes).encode('utf-8')).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def norm(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())


def overlap(left: str, right: str) -> float:
    a, b = set(norm(left)), set(norm(right))
    stop = {'the','and','for','with','from','into','that','this','are','was','were','its','using','use','given','record','result'}
    a -= stop
    b -= stop
    return len(a & b) / max(1, len(a))


def valid_review(review: dict[str, Any], passage_ids: list[str], passages: dict[str, dict[str, Any]]) -> bool:
    if not review.get('reviewer') or not review.get('reviewed_at'):
        return False
    expected={pid:passages[pid]['text_sha256'] for pid in passage_ids if pid in passages}
    if len(expected)!=len(passage_ids) or review.get('passage_hashes')!=expected:
        return False
    flagged={pid for pid in passage_ids if passages[pid].get('quality_flags')}
    return flagged.issubset(set(review.get('visually_checked_passage_ids',[])))


def valid_claim_review(review, claim, record, passages):
    """Bind a review to the current field value as well as the source passages."""
    current = record
    try:
        for part in claim['field_path'].strip('/').split('/'):
            current = current[int(part)] if isinstance(current, list) else current[part]
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    if current != claim['text']:
        return False
    binding = {'field_path': claim['field_path'], 'text': claim['text'], 'kind': claim['kind']}
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    if review.get('claim_sha256') != digest:
        return False
    pids = review.get('passage_ids', [])
    if not pids or not valid_review(review, pids, passages):
        return False
    quotes = review.get('quotes', [])
    if {q.get('passage_id') for q in quotes} != set(pids):
        return False
    for quote in quotes:
        text = ' '.join(quote.get('exact_quote', '').split())
        if not text or text not in ' '.join(passages[quote['passage_id']]['text'].split()):
            return False
    return True


def build_graph() -> dict[str, Any]:
    payload = read_json(ROOT/'data/chemistry_experiments.json')
    manuals = read_json(ROOT/'evidence/manuals.json')
    sections = read_json(ROOT/'evidence/sections.json')
    passages = {p['passage_id']:p for p in load_jsonl(ROOT/'evidence/passages.jsonl')}
    reviews = read_json(ROOT/'evidence/reviews.json')
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    section_by_id = {s['section_id']:s for s in sections}
    records = payload['experiments']
    counts = Counter()

    manual_ids={}
    for manual in manuals:
        mid = 'manual:'+manual['sha256'][:16]
        manual_ids[manual['filename']]=mid
        nodes.append({'id':mid,'type':'manual','filename':manual['filename'],'edition':manual.get('edition'),
            'sha256':manual['sha256'],'page_count':manual['page_count']})

    for p in passages.values():
        nodes.append({'id':p['passage_id'],'type':'passage','manual_filename':p['manual_filename'],
            'manual_sha256':p['manual_sha256'],'edition':p.get('edition'),'pdf_page':p['pdf_page'],
            'printed_page':p.get('printed_page'),'printed_page_basis':p.get('printed_page_basis'),
            'section_id':p.get('section_id'),'section_heading':p.get('section_heading'),
            'text_sha256':p['text_sha256'],'quality_flags':p.get('quality_flags',[]),
            'extraction_review':'needs_review'})
        edges.append({'from':manual_ids[p['manual_filename']],'type':'HAS_PASSAGE','to':p['passage_id'],
            'status':'extracted_needs_review'})

    for record in records:
        eid=record['experiment_id']
        nodes.append({'id':eid,'type':'experiment','title':record['title'],'subject':record['subject'],
            'class_level':record['class_level'],'catalog_status':record.get('status'),
            'source_verification':record.get('evidence',{}).get('source_verification','unverified'),
            'retrieval_eligibility':record.get('evidence',{}).get('retrieval_eligibility','review_required'),
            'video_readiness':record.get('evidence',{}).get('video_readiness','review_required')})
        linked=[]
        for sid in record.get('evidence',{}).get('section_ids',[]):
            section=section_by_id.get(sid)
            if not section:
                continue
            review=reviews.get('sections',{}).get(sid,{})
            approved=(review.get('status')=='approved_for_retrieval'
                and valid_review(review,section['passage_ids'],passages)
                and review.get('manual_sha256')==next(m['sha256'] for m in manuals if m['filename']==section['manual_filename']))
            section_node={'id':sid,'type':'section','experiment_id':eid,'heading':section['heading'],
                'manual_filename':section['manual_filename'],'printed_start':section['printed_start'],
                'printed_end':section['printed_end'],'proposal_status':section['review_status'],
                'review_status':'approved_for_retrieval' if approved else 'candidate_needs_human_review'}
            nodes.append(section_node)
            edges.append({'from':eid,'type':'HAS_SECTION' if approved else 'HAS_CANDIDATE_SECTION','to':sid,
                'status':'approved_for_retrieval' if approved else 'candidate_needs_human_review'})
            linked.append(section)
            for pid in section['passage_ids']:
                if pid not in passages:
                    continue
                edges.append({'from':sid,'type':'CONTAINS_PASSAGE','to':pid,
                    'status':'approved_for_retrieval' if approved else 'extracted_needs_review'})

        if linked:
            counts['candidate_section'] += 1
        else:
            counts['no_link_in_supplied_pdfs'] += 1
            nodes[-1]['source_status']='no_link_in_supplied_pdfs'

        claims=[]
        for original in record.get('evidence',{}).get('claims',[]):
            claim=dict(original)
            match=re.match(r'^/procedure_steps/(\d+)/',claim['field_path'])
            if match:
                step=record['procedure_steps'][int(match.group(1))]
                claim['scene_ids']=step.get('scene_ids',[])
                claim['scene_link_status']=step.get('scene_link_status','needs_review')
            elif claim['field_path'].startswith('/scenes/'):
                match=re.match(r'^/scenes/(\d+)/',claim['field_path'])
                if match:
                    claim['scene_ids']=[record['scenes'][int(match.group(1))]['scene_id']]
            claims.append(claim)
        for claim in claims:
            nodes.append({'id':claim['claim_id'],'type':'claim','experiment_id':eid,**claim,
                'review_status':claim.get('review_status','needs_review')})
            edges.append({'from':eid,'type':'HAS_CLAIM','to':claim['claim_id']})
            claim_review=reviews.get('claims',{}).get(claim['claim_id'],{})
            for section in linked:
                section_review=reviews.get('sections',{}).get(section['section_id'],{})
                for pid in section['passage_ids']:
                    p=passages.get(pid)
                    if not p:
                        continue
                    score=overlap(claim['text'],p['text'])
                    approved_ids=claim_review.get('passage_ids',[])
                    # Recompute for every passage; approvals must never leak between pages.
                    approved=(section_review.get('status')=='approved_for_retrieval'
                        and valid_review(section_review,section['passage_ids'],passages)
                        and section_review.get('manual_sha256')==next(m['sha256'] for m in manuals if m['filename']==section['manual_filename'])
                        and pid in approved_ids and claim_review.get('status')=='verified'
                        and valid_claim_review(claim_review,claim,record,passages))
                    if score >= 0.12 or approved:
                        edges.append({'from':claim['claim_id'],'type':'SUPPORTED_BY' if approved else 'CANDIDATE_SUPPORT',
                            'to':pid,'score':round(score,4),
                            'status':'verified' if approved else 'candidate_needs_human_review'})
    digest=evidence_fingerprint(ROOT)
    return {'schema_version':GRAPH_VERSION,'build_fingerprint':digest,
        'semantics':'CANDIDATE_SUPPORT edges are lexical suggestions. SUPPORTED_BY requires an explicit claim-bound review with exact source quotes; consult evidence/reviews.json for agent versus human review. Source support is not scientific or visual certification.',
        'counts':{'experiments':len(records),'sections':len(sections),'passages':len(passages),
            'claims':sum(1 for n in nodes if n['type']=='claim'),'edges':len(edges),**counts},
        'nodes':nodes,'edges':edges}


def main() -> None:
    graph=build_graph()
    target=ROOT/'evidence/evidence_graph.json'
    target.write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(graph['counts'],indent=2))


if __name__=='__main__':
    main()
