"""Copy only claim-bound, hash-checked review decisions into canonical evidence fields."""
from __future__ import annotations

import json
from pathlib import Path

from build_evidence_graph import ROOT, load_jsonl, read_json, valid_review, valid_claim_review


def main() -> None:
    data_path=ROOT/'data/chemistry_experiments.json'
    payload=read_json(data_path)
    reviews=read_json(ROOT/'evidence/reviews.json')
    manuals=read_json(ROOT/'evidence/manuals.json')
    sections=read_json(ROOT/'evidence/sections.json')
    passages={p['passage_id']:p for p in load_jsonl(ROOT/'evidence/passages.jsonl')}
    manual_hash={m['filename']:m['sha256'] for m in manuals}
    section_by_id={s['section_id']:s for s in sections}
    approved_sections={}
    for sid,entry in reviews.get('sections',{}).items():
        section=section_by_id.get(sid)
        if section and entry.get('status')=='approved_for_retrieval' and valid_review(entry,section['passage_ids'],passages) \
                and entry.get('manual_sha256')==manual_hash.get(section['manual_filename']):
            approved_sections[sid]=section

    verified_claims=0
    eligible_records=0
    for record in payload['experiments']:
        evidence=record['evidence']
        linked_sections=[section_by_id[sid] for sid in evidence.get('section_ids',[]) if sid in section_by_id]
        allowed_passages={pid for section in linked_sections if section['section_id'] in approved_sections for pid in section['passage_ids']}
        for claim in evidence['claims']:
            entry=reviews.get('claims',{}).get(claim['claim_id'],{})
            pids=entry.get('passage_ids',[])
            accepted=(entry.get('status')=='verified' and bool(pids) and set(pids)<=allowed_passages
                and valid_claim_review(entry,claim,record,passages))
            if accepted:
                claim['passage_ids']=pids
                claim['review_status']='verified'
                verified_claims+=1
            else:
                claim['passage_ids']=[]
                claim['review_status']='rejected' if entry.get('status')=='rejected' else 'needs_review'

        all_claims=bool(evidence['claims']) and all(c['review_status']=='verified' for c in evidence['claims'])
        any_claim=any(c['review_status']=='verified' for c in evidence['claims'])
        if all_claims:
            evidence['source_verification']='verified'
        elif any_claim:
            evidence['source_verification']='partially_verified'
        elif linked_sections:
            evidence['source_verification']='unverified'
        else:
            evidence['source_verification']='no_link_in_supplied_pdfs'
        evidence['retrieval_eligibility']='eligible' if all_claims else 'review_required'
        scene_links=all(step.get('scene_link_status')=='verified' and step.get('scene_ids') for step in record['procedure_steps'])
        evidence['video_readiness']='ready' if all_claims and scene_links else 'review_required'
        all_pids=sorted({pid for claim in evidence['claims'] if claim['review_status']=='verified' for pid in claim['passage_ids']})
        for source in record['sources']:
            source['passage_ids']=all_pids
            source['verification_status']='verified' if all_claims and all_pids else 'needs_page_check'
        if evidence['retrieval_eligibility']=='eligible':
            eligible_records+=1

    data_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Applied hash-checked reviews: {verified_claims} verified claims across {eligible_records} retrieval-eligible records.')


if __name__=='__main__':
    main()
