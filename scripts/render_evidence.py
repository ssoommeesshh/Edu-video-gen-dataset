"""Render selected source pages for visual review, without altering PDFs."""
import pymupdf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
out = ROOT/'tmp/pdfs'
out.mkdir(parents=True,exist_ok=True)
for filename,pages in [('Physics_Laboratory_Manual_11-12_E.pdf',[122,123,124]),('Manual_01.pdf',[28,29,30,31])]:
    doc = pymupdf.open(ROOT/filename)
    for n in pages:
        doc[n-1].get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(out/f'{Path(filename).stem}-{n}.png')
        print(f'PDF {n}:\n{doc[n-1].get_text()}')
