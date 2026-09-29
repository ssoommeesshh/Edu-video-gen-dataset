"""Search the catalog, then return candidate/approved source paths and exact text."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .build_evidence_graph import ROOT, load_jsonl, read_json, evidence_fingerprint
    from .query_rag import retrieve_with_status
except ImportError:
    from build_evidence_graph import ROOT, load_jsonl, read_json, evidence_fingerprint
    from query_rag import retrieve_with_status


def search(query: str, top_n: int = 3, experiment_id: str | None = None) -> dict[str, Any]:
    index_path=ROOT/'rag_index_matrix.npz'
    vectorizer_path=ROOT/'rag_vectorizer.pkl'
    meta_path=ROOT/'rag_index_meta.json'
    if not all(p.exists() for p in [index_path,vectorizer_path,meta_path]):
        raise FileNotFoundError('Build the catalog index first: python scripts/build_exports.py; python scripts/build_rag_index.py')
    import pickle
    from scipy import sparse
    with vectorizer_path.open('rb') as handle:
        vectorizer=pickle.load(handle)
    matrix=sparse.load_npz(str(index_path))
    docs=json.loads(meta_path.read_text(encoding='utf-8'))
    retrieval=retrieve_with_status(query,vectorizer,matrix,docs,top_n=max(top_n+19,20))
    graph=read_json(ROOT/'evidence/evidence_graph.json')
    fingerprint=evidence_fingerprint(ROOT)
    if graph.get('build_fingerprint')!=fingerprint:
        raise ValueError('Evidence graph is stale. Run scripts/build_evidence_graph.py first.')
    pages={p['passage_id']:p for p in load_jsonl(ROOT/'evidence/passages.jsonl')}
    nodes={n['id']:n for n in graph['nodes']}
    edges=graph['edges']
    matches=[]
    ranked=retrieval['results']
    selected=ranked[:top_n]
    if experiment_id is not None:
        document=next((d for d in docs if d['id']==experiment_id),None)
        if document is None:
            raise ValueError(f'Unknown experiment_id: {experiment_id}')
        selected=[{'id':experiment_id,'score':None,**document['metadata']}]
        retrieval={**retrieval,'status':'explicit_selection','message':f'Using selected experiment {experiment_id}; evidence status is checked separately.'}
    reviews=read_json(ROOT/'evidence/reviews.json').get('claims',{})
    for candidate in selected:
        eid=candidate['id']
        section_edges=[e for e in edges if e['from']==eid and e['type'] in {'HAS_CANDIDATE_SECTION','HAS_SECTION'}]
        sections=[]
        source_passages={}
        for edge in section_edges:
            section=nodes[edge['to']]
            passages=[]
            for contains in [e for e in edges if e['from']==section['id'] and e['type']=='CONTAINS_PASSAGE']:
                p=pages[contains['to']]
                passage={'passage_id':p['passage_id'],'manual_filename':p['manual_filename'],
                    'edition':p.get('edition'),'manual_sha256':p['manual_sha256'],
                    'pdf_page':p['pdf_page'],'printed_page':p.get('printed_page'),
                    'section_heading':p.get('section_heading'),'quality_flags':p.get('quality_flags',[]),
                    'review_status':contains['status'],'exact_quote':p['text']}
                passages.append({k:v for k,v in passage.items() if k!='exact_quote'})
                source_passages[p['passage_id']]=passage
            sections.append({'section_id':section['id'],'heading':section['heading'],
                'manual_filename':section['manual_filename'],'review_status':section['review_status'],
                'passages':passages})
        claim_nodes=[n for n in graph['nodes'] if n['type']=='claim' and n['experiment_id']==eid]
        claims=[]
        for claim in claim_nodes:
            claim_edges=[e for e in edges if e['from']==claim['id'] and e['type'] in {'SUPPORTED_BY','CANDIDATE_SUPPORT'}]
            claim_passages=[]
            for edge in claim_edges:
                p=pages[edge['to']]
                claim_passages.append({'passage_id':p['passage_id'],'printed_page':p.get('printed_page'),
                    'score':edge['score'],'status':edge['status']})
            claims.append({'claim_id':claim['claim_id'],'kind':claim['kind'],'text':claim['text'],
                'scene_ids':claim.get('scene_ids',[]),'scene_link_status':claim.get('scene_link_status'),
                'support_status':'verified' if any(p['status']=='verified' for p in claim_passages) else 'needs_review',
                'review_kind':reviews.get(claim['claim_id'],{}).get('review_kind','unspecified'),
                'human_review_status':reviews.get(claim['claim_id'],{}).get('human_review_status','pending'),
                'passages':claim_passages})
        review_count=sum(c['support_status']=='verified' for c in claims)
        matches.append({'experiment_id':eid,'title':candidate['title'],'subject':candidate['subject'],
            'class_level':candidate['class_level'],'retrieval_score':candidate['score'],
            'source_verification':nodes[eid].get('source_verification','unverified'),
            'retrieval_eligibility':nodes[eid].get('retrieval_eligibility','review_required'),
            'video_readiness':nodes[eid].get('video_readiness','review_required'),
            'source_status':'has_candidate_sections' if sections else 'no_link_in_supplied_pdfs',
            'sections':sections,'source_passages':list(source_passages.values()),'claims':claims,
            'confidence_status':'source_verified' if claims and review_count==len(claims) else 'candidate_needs_human_review' if sections else 'no_link_in_supplied_pdfs'})
    related=[r for r in ranked if r['id'] not in {m['experiment_id'] for m in matches}]
    if matches:
        same_subject=[r for r in related if r.get('subject')==matches[0]['subject']]
        related=same_subject or related
        related=sorted(related,key=lambda r:(r.get('class_level')!=matches[0]['class_level'],-r['score']))
    return {'query':query,'retrieval_status':retrieval['status'],'retrieval_message':retrieval['message'],
        'matches':matches,'nearby_experiments':[
            {'experiment_id':r['id'],'title':r['title'],'subject':r.get('subject'),'class_level':r.get('class_level'),
             'score':r['score'],'relatedness_basis':'catalog retrieval similarity; navigation only'}
            for r in related[:5]],
        'prompt_eligible_experiment_ids':[m['experiment_id'] for m in matches if m['confidence_status']=='source_verified']}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('query')
    parser.add_argument('--top-n',type=int,default=1)
    parser.add_argument('--experiment-id',help='Inspect the explicitly selected catalog record instead of the top similarity match')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.top_n<1:
        raise ValueError('--top-n must be positive')
    output_text=json.dumps(search(args.query,args.top_n,args.experiment_id),ensure_ascii=False,indent=2)+'\n'
    if args.output:
        output=args.output if args.output.is_absolute() else ROOT/args.output
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(output_text,encoding='utf-8')
        print(f'Saved evidence query to {output}')
    else:
        print(output_text,end='')


if __name__=='__main__':
    main()
