"""Draft Codabench scoring entry point. Not yet run on Codabench.

Usage: scoring.py INPUT_DIR OUTPUT_DIR, where INPUT_DIR holds ref/ and res/.
"""

import sys
from pathlib import Path

from roverloom.competition import score

if __name__ == "__main__":
    input_dir, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
    print(score(input_dir / "ref", input_dir / "res", output_dir))
