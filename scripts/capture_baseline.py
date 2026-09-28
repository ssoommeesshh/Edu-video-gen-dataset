"""Run the original retrieval code/index from a pinned git revision against the new benchmark."""
import hashlib
import json
import pickle
import subprocess
import tempfile
import types
from pathlib import Path
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'd366de4a46caad4af8b54619e163658200c2d02e'


def git_bytes(name):
    return subprocess.check_output(['git', 'show', f'{REVISION}:{name}'], cwd=ROOT)


def main():
    old = types.ModuleType('baseline_query')
    old.__file__ = str(ROOT/'scripts/query_rag.py')
    exec(compile(git_bytes('scripts/query_rag.py'), old.__file__, 'exec'), old.__dict__)
    vectorizer = pickle.loads(git_bytes('rag_vectorizer.pkl'))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'matrix.npz'
        path.write_bytes(git_bytes('rag_index_matrix.npz'))
        matrix = sparse.load_npz(path)
    docs = json.loads(git_bytes('rag_index_meta.json'))
    cases = json.loads((ROOT/'data/retrieval_benchmark.json').read_text())['cases']
    rows = []
    for case in cases:
        rows.append({'case_id': case['case_id'], 'query': case['query'],
            'candidates': old.rank_documents(case['query'], vectorizer, matrix, docs, top_n=3),
            'outcome': 'supported', 'note': 'Legacy accepted every query; filters unsupported.'})
    result = {'revision': REVISION, 'benchmark_sha256': hashlib.sha256((ROOT/'data/retrieval_benchmark.json').read_bytes()).hexdigest(),
        'rows': rows, 'invalid_legacy_label': {'query':'acid-base titration','old_expected_id':'chem_12_1002',
        'correction':'ambiguous: multiple titrations; enthalpy of neutralisation is not a titration'}}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/baseline_retrieval.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'Captured {len(rows)} baseline queries at {REVISION}')


if __name__ == '__main__':
    main()
