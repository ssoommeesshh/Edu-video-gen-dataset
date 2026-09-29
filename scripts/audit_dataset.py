"""Reproducible audit; no changes to canonical records."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(path):
    raw = path.read_bytes()
    records = json.loads(raw)['experiments']
    required = json.loads((ROOT / 'schema/experiment.schema.json').read_text())['required']
    findings = []
    for r in records:
        findings.append({
            'experiment_id': r['experiment_id'],
            'missing_fields': [k for k in required if k not in r],
            'vague_observations': [s['step_id'] for s in r.get('procedure_steps', [])
                if re.search(r'\b(record|noted|ready|observe|tabul|expected|can be|obtained|changes)\w*', s.get('observation', ''), re.I)],
            'unlinked_steps': [s['step_id'] for s in r.get('procedure_steps', []) if not s.get('scene_ids')],
            'unreviewed_scene_links': [s['step_id'] for s in r.get('procedure_steps', []) if s.get('scene_link_status') != 'verified'],
            'unlocated_sources': [s['source_id'] for s in r.get('sources', []) if not s.get('passage_ids')],
            'placeholder_images': [s['image_asset_id'] for s in r.get('image_assets', []) if s.get('license_status') == 'placeholder'],
        })
    return {'input_sha256': hashlib.sha256(raw).hexdigest(), 'record_count': len(records),
        'duplicate_ids': [k for k,v in Counter(r['experiment_id'] for r in records).items() if v > 1],
        'subject_counts': dict(Counter(r['subject'] for r in records)),
        'heuristics': 'Vague observation regex flags are review candidates, not scientific judgments.',
        'totals': {k: sum(len(f[k]) for f in findings) for k in findings[0] if k != 'experiment_id'},
        'records': findings}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, default=ROOT/'data/chemistry_experiments.json')
    p.add_argument('--output', type=Path, default=ROOT/'reports/baseline_audit.json')
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    result = audit(a.input)
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}, indent=2))
