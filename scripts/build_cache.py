"""Parse the wide PRISM CSVs once and cache them as float32 matrices.

The Pennsylvania temperature file alone is 1.6 GB of CSV; parsing it takes
minutes, so every downstream script reads the cache instead.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee.config import NY_PPT_CSV, NY_TMEAN_CSV, PA_PPT_CSV, PA_TMEAN_CSV
from applebee.weather import load_weather

TARGETS = [
    ("ny_tmean", NY_TMEAN_CSV),
    ("ny_ppt", NY_PPT_CSV),
    ("pa_tmean", PA_TMEAN_CSV),
    ("pa_ppt", PA_PPT_CSV),
]


def main() -> None:
    for key, path in TARGETS:
        if not path.exists():
            print(f"MISSING {key}: {path}", flush=True)
            continue
        size_mb = path.stat().st_size / 1e6
        print(f"building {key} from {path.name} ({size_mb:,.0f} MB)...", flush=True)
        start = time.time()
        grid = load_weather(path, cache_key=key)
        print(
            f"  {key}: {grid.values.shape[0]:,} cells x {grid.values.shape[1]:,} days "
            f"[{grid.dates[0].date()} .. {grid.dates[-1].date()}] "
            f"in {time.time() - start:.0f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
