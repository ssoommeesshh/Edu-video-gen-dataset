"""Extract page text verbatim, with conservative quality flags and content-addressed IDs."""
import argparse
import hashlib
import json
import re
import warnings
from pathlib import Path
import pypdf
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def extract(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        with warnings.catch_warnings(record=True) as caught:
            text = page.extract_text() or ''
        flags = []
        if len(re.sub(r'\s', '', text)) < 80:
            flags.append('sparse_text_check_scan_or_blank')
        if '\ufffd' in text or any(0xE000 <= ord(c) <= 0xF8FF for c in text):
            flags.append('encoding_or_symbol_review')
        if caught:
            flags.append('extraction_warning')
        # Prefer publisher footer. Physics content pages have a running folio
        # without the DTP footer, calibrated against contents and PDF p122 -> p94.
        folios = re.findall(r'\.indd\s+(\d+)\s+\d{2}-\d{2}-\d{4}', text)
        printed = folios[-1] if len(set(folios)) == 1 else None
        basis = 'publisher_indd_footer' if printed else None
        if printed is None and path.name == 'Physics_Laboratory_Manual_11-12_E.pdf' and 29 <= number <= 226:
            printed = str(number - 28)
            basis = 'publisher_running_folio_offset_calibrated_pdf_122_printed_94'
        if printed is None:
            flags.append('printed_page_unresolved')
        pages.append({'manual_filename': path.name, 'manual_sha256': digest,
            'pdf_page': number, 'printed_page': printed,
            'printed_page_basis': basis,
            'passage_id': f'{path.stem}:{digest[:12]}:p{number:04d}',
            'section_id': None, 'section_heading': None,
            'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'quality_flags': flags, 'review_status': 'needs_review'})
    edition = '\n'.join(p['text'] for p in pages[:5])
    match = re.search(r'First Edition\s+(.+?)(?=PD |©)', edition, re.S)
    edition = match.group(0).strip() if match else None
    for p in pages:
        p['edition'] = edition
    return {'filename': path.name, 'sha256': digest, 'page_count': len(pages),
        'edition': edition, 'extractor': f'pypdf {pypdf.__version__}',
        'flagged_pages': [p['pdf_page'] for p in pages if p['quality_flags']],
        'limitations': 'No OCR. Formula, table, diagram and reading-order accuracy require visual review.'}, pages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdfs', nargs='+', type=Path)
    args = parser.parse_args()
    out = ROOT/'evidence'
    out.mkdir(exist_ok=True)
    manuals, passages = [], []
    for path in args.pdfs:
        manual, pages = extract(path)
        manuals.append(manual)
        passages.extend(pages)
    (out/'manuals.json').write_text(json.dumps(manuals, indent=2)+'\n', encoding='utf-8')
    (out/'pages.jsonl').write_text(''.join(json.dumps(p, ensure_ascii=False)+'\n' for p in passages), encoding='utf-8')
    print(json.dumps([{'filename':m['filename'], 'pages':m['page_count'], 'flagged':len(m['flagged_pages'])} for m in manuals]))


if __name__ == '__main__':
    main()
