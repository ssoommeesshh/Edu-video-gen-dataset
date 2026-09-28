"""Propose catalog-to-section links from the supplied manuals' contents pages.

Ranges below are printed folios transcribed from the contents, not PDF offsets.
All proposals require review; only explicit review entries approve retrieval.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHEM = [(101,17,18),(102,19,20),(103,21,22),(201,23,24),(202,25,28),
    (203,29,30),(204,31,34),(205,35,39),(206,40,44),(301,45,67),
    (401,68,70),(402,71,74),(403,75,77),(501,81,82),(502,83,84),
    (601,85,86),(602,87,87),(603,88,89),(604,90,91),(605,92,93),
    (606,94,95),(607,96,97),(701,98,99),(702,100,102),(801,104,105),
    (802,106,106),(803,107,109),(901,111,112),(902,113,113),
    (903,114,115),(904,116,117),(1001,120,122),(1002,123,124),(1101,125,128)]
PHYSICS = {
    (11,0): [1,7,12,16,19,23,27,31,33,37,41,45,48,52,56,62],
    (11,100): [62,64,67,70,73,76,79,82,84,86,88,90,93],
    (12,0): [94,97,103,107,111,114,119,125,129,133,138,141,145,149,156,159,161,165],
    (12,100): [165,167,169,174,176,177,180,182,185,187,189,190,191,195,197],
}


def main():
    pages = [json.loads(line) for line in (ROOT/'evidence/pages.jsonl').read_text(encoding='utf-8').splitlines()]
    records = {r['experiment_id']:r for r in json.loads((ROOT/'data/chemistry_experiments.json').read_text())['experiments']}
    specs = [(f'chem_12_{n}', 'Manual_01.pdf', start, end, f'Experiment {n//100}.{n%100}') for n,start,end in CHEM]
    for (level,offset),starts in PHYSICS.items():
        for n,(start,stop) in enumerate(zip(starts, starts[1:]),1):
            specs.append((f'phy_{level}_{offset+n:03d}', 'Physics_Laboratory_Manual_11-12_E.pdf', start, stop-1,
                f'Class {level} '+('Activity' if offset else 'Experiment')+f' {n}'))
    sections = []
    for eid, filename, start, end, heading in specs:
        selected = [p for p in pages if p['manual_filename']==filename and p['printed_page'] is not None
            and start<=int(p['printed_page'])<=end and '.indd' in p['text']
            and 'Prelims' not in p['text'] and 'Cover' not in p['text']]
        section_id = eid+':manual_section'
        for p in selected:
            p['section_id'], p['section_heading'] = section_id, heading
        sections.append({'section_id':section_id,'experiment_id':eid,'manual_filename':filename,
            'heading':heading,'catalog_title':records[eid]['title'], 'printed_start':start,'printed_end':end,
            'passage_ids':[p['passage_id'] for p in selected],
            'review_status':'needs_review','human_review':'pending',
            'basis':'Contents transcription; page boundaries and title alignment need human confirmation.'})
    (ROOT/'evidence/sections.json').write_text(json.dumps(sections,indent=2)+'\n',encoding='utf-8')
    (ROOT/'evidence/passages.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in pages),encoding='utf-8')
    print(f'Proposed {len(sections)} sections; {sum(not s["passage_ids"] for s in sections)} without extracted pages')


if __name__ == '__main__':
    main()
