"""Draft Codabench ingestion entry point. Not yet run on Codabench.

Usage: ingestion.py REFERENCE_DIR OUTPUT_DIR SUBMISSION_DIR.
Requires an isolated container. See docs/competition-io.md.
"""

import sys
from pathlib import Path

from roverloom.competition import ingest

if __name__ == "__main__":
    reference, output, submission = (Path(arg) for arg in sys.argv[1:4])
    print(ingest(submission.resolve(), reference, output))
