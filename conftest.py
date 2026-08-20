"""Put the repository root on the import path for tests.

The package is not installed -- everything here runs from a clone -- so
``import applebee`` needs the root on ``sys.path``. Running ``python -m pytest``
adds the working directory and hides the problem; running ``pytest`` does not,
which is how CI found it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
