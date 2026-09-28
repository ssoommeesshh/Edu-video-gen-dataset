"""Run repository Python scripts using a single environment, with explicit script selection."""
import runpy
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parent
script = (root / sys.argv[1]).resolve()
if script.parent != root or script.suffix != '.py' or script == Path(__file__).resolve():
    raise ValueError('Select a Python script directly in scripts/')
sys.argv = [str(script), *sys.argv[2:]]
runpy.run_path(str(script), run_name='__main__')
