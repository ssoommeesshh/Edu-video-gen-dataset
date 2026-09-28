"""Developer inspection helper; does not assign verification status."""
from pathlib import Path
from pypdf import PdfReader
import sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
for filename in ['Manual_01.pdf', 'Physics_Laboratory_Manual_11-12_E.pdf']:
    reader = PdfReader(ROOT/filename)
    print(filename, len(reader.pages), reader.metadata)
    for i in list(range(min(12,len(reader.pages)))):
        print('\nPDF PAGE', i+1, (reader.pages[i].extract_text() or '')[:5000])
