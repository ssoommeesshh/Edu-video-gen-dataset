"""Add reviewable links without rewriting legacy scientific content; idempotent."""
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def migrate(payload, sections):
    result = copy.deepcopy(payload)
    lookup = {s['experiment_id']:s for s in sections}
    for r in result['experiments']:
        section = lookup.get(r['experiment_id'])
        if 'evidence' in r:
            r['evidence']['section_ids'] = [section['section_id']] if section else []
            if section and r['evidence'].get('source_verification') == 'no_link_in_supplied_pdfs':
                r['evidence']['source_verification'] = 'unverified'
            if not section and r['evidence'].get('source_verification') == 'unverified':
                r['evidence']['source_verification'] = 'no_link_in_supplied_pdfs'
            continue
        scene_ids = [s['scene_id'] for s in r['scenes']]
        claims = []
        def claim(path, text, kind):
            claims.append({'claim_id':f'{r["experiment_id"]}:c{len(claims)+1:03d}',
                'field_path':path,'text':text,'kind':kind,'passage_ids':[], 'review_status':'needs_review'})
        for i,step in enumerate(r['procedure_steps']):
            step['scene_ids'] = scene_ids if len(scene_ids)==1 else []
            step['scene_link_status'] = 'needs_review'
            step['presentation'] = 'overlay' if re.search(r'\b(plot|calculate|record|tabulate|classify|report|compare)\b',step['instruction'],re.I) else 'physical'
            claim(f'/procedure_steps/{i}/instruction',step['instruction'],'action')
            claim(f'/procedure_steps/{i}/observation',step['observation'],'observation')
        for field,kind in [('materials','material'),('safety_notes','safety')]:
            for i,value in enumerate(r.get(field,[])):
                claim(f'/{field}/{i}',value,kind)
        for i,scene in enumerate(r['scenes']):
            claim(f'/scenes/{i}/description',scene['description'],'scene')
            for j,value in enumerate(scene['visible_actions']):
                claim(f'/scenes/{i}/visible_actions/{j}',value,'action')
        # Quantity claims are separate even when embedded in an action/material claim.
        for c in list(claims):
            if re.search(r'\d',c['text']):
                claim(c['field_path'],c['text'],'quantity')
        r['evidence'] = {'section_ids':[section['section_id']] if section else [],
            'source_verification':'unverified' if section else 'no_link_in_supplied_pdfs', 'retrieval_eligibility':'review_required',
            'video_readiness':'review_required', 'claims':claims,
            'legacy_source_statuses':[{'source_id':s['source_id'],'verification_status':s['verification_status']} for s in r['sources']]}
        for source in r['sources']:
            source['verification_status'] = 'needs_page_check'
            source['passage_ids'] = []
    result['dataset_version'] = '0.4.0'
    return result


def main():
    path = ROOT/'data/chemistry_experiments.json'
    before = path.read_bytes()
    original = json.loads(before)
    result = migrate(original,json.loads((ROOT/'evidence/sections.json').read_text()))
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report = ROOT/'reports/migration.json'
    if not report.exists():
        report.write_text(json.dumps({'input_sha256':hashlib.sha256(before).hexdigest(),
            'input_version':original['dataset_version'],'output_version':result['dataset_version'],
            'ids_preserved':[r['experiment_id'] for r in original['experiments']]==[r['experiment_id'] for r in result['experiments']],
            'policy':'Preserve all legacy prose and IDs. Preserve old source statuses in evidence. No claim is automatically verified. Single-scene links are proposals; multi-scene mappings remain unresolved.'},indent=2)+'\n')
    print('Migrated records; all scientific claims remain unverified.')


if __name__ == '__main__':
    main()
