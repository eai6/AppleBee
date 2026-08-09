"""Build the Lonsdorf spring forage index for a region from the Cropland Data Layer.

Downloads the CONUS-wide CDL for each year (~1.9 GB from USDA), reclassifies
land-cover classes with Koh et al. (2016) expert spring values, and takes the
area-weighted mean within 1/3/5 km of each grid-cell centre.

    python scripts/build_forage.py --years 2013 2018 --region northeast --dry-run
    python scripts/build_forage.py --years 2013 2018 --region northeast

**The national raster is the default, and should stay that way.** The
alternative -- 16 per-state rasters from the GMU service, mosaicked -- was tried
first and is worse on every axis:

* *Completeness.* State rasters stop at the state line, so buffers straddling a
  border lose whatever falls outside. National gains 528 cells over the mosaic
  in the Northeast and loses none.
* *Accuracy.* Validated against the archived Pennsylvania index, national scores
  r = 0.979 / 0.978 / 0.976 at 1/3/5 km against the mosaic's 0.973 / 0.970 /
  0.966, because there is no Background padding to renormalise around.
* *Reliability.* The per-state service dropped ten states from the 2015 build and
  seven from 2018, then returned 503 for a day. One national file has no partial
  failure mode.

`--source state` is kept only for reproducing those earlier builds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee.acquire import cdl, grid  # noqa: E402
from applebee.config import DATA, INPUTS  # noqa: E402

REGIONS = {"northeast": grid.NORTHEAST, "pennsylvania": grid.PENNSYLVANIA,
           "conus": grid.CONUS}

# Any PRISM day gives the land mask; it is identical across days.
LAND_MASK_RASTER = (
    Path(__file__).resolve().parent.parent
    / "archives/data/prism/PRISM_tmean_stable_4kmD2_20150501_bil"
    / "PRISM_tmean_stable_4kmD2_20150501_bil.bil"
)

# States mosaicked in for border completeness even though the region excludes them.
NEIGHBOURS = {"northeast": ("OH", "KY", "NC"),
              "pennsylvania": ("NY", "NJ", "MD", "DE", "WV", "OH"),
              "conus": ()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", nargs=2, type=int, default=[2013, 2018],
                        metavar=("FIRST", "LAST"), help="inclusive year range")
    parser.add_argument("--region", default="northeast", choices=sorted(REGIONS))
    parser.add_argument("--radii", nargs="+", type=int, default=list(cdl.DEFAULT_RADII_M),
                        help="foraging radii in metres")
    parser.add_argument("--clip-to-states", action="store_true",
                        help="clip cells to real state boundaries instead of the bounding box")
    parser.add_argument("--raster-dir", type=Path, default=DATA / "raw" / "cdl")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--source", default="national", choices=("national", "state"),
                        help="'national' (default) pulls one CONUS raster per year from USDA "
                             "(~1.9 GB): no mosaic, no state-border artefacts, no dependence on "
                             "the GMU per-state service. 'state' is the legacy 16-raster mosaic, "
                             "kept only for reproducing earlier builds")
    parser.add_argument("--discard-rasters", action="store_true",
                        help="delete each year's rasters once computed, so peak disk is one "
                             "year (~1.3 GB) instead of all six (~8 GB). The CDL service is "
                             "fast and unthrottled, so re-fetching later is cheap")
    parser.add_argument("--dry-run", action="store_true", help="report cost and exit")
    args = parser.parse_args()

    region = REGIONS[args.region]
    years = list(range(args.years[0], args.years[1] + 1))
    states = tuple(sorted(set(region.states) | set(NEIGHBOURS[region.name])))
    out = args.out or INPUTS / "forage" / f"{region.name}_forage_spring_lonsdorf.csv"

    print(f"region  : {region.name}")
    print(f"years   : {years[0]}-{years[-1]}  ({len(years)} years)")
    print(f"states  : {len(states)} mosaicked -- {', '.join(states)}")
    print(f"rasters : {len(states) * len(years)} state-years "
          f"(~{len(states) * len(years) * 60 / 1024:.1f} GB, one-off)")

    if args.region == "conus":
        cells = grid.land_cells(LAND_MASK_RASTER)
        print("cells   : CONUS land mask (ocean and nodata excluded)")
    elif args.clip_to_states:
        print(f"\nresolving state boundaries ...")
        cells = grid.cells_for_states(region.states)
    else:
        cells = region.cells()
    print(f"cells   : {len(cells):,}  -> {len(cells) * len(years):,} cell-years to compute")
    print(f"output  : {out}")

    if args.dry_run:
        print("\ndry run; nothing downloaded.")
        return

    # A year at a time: fetch, compute, optionally discard. Keeps peak disk to
    # one year of rasters and means an interrupted run keeps completed years.
    import time

    import pandas as pd

    geometry = cells[["col", "row", "lon", "lat"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    partial_dir = out.parent / f"{region.name}_forage_by_year"
    partial_dir.mkdir(exist_ok=True)
    frames = []

    for year in years:
        partial = partial_dir / f"{year}.csv"
        if partial.exists():
            print(f"\n{year}: already computed, reusing {partial.name}")
            frames.append(pd.read_csv(partial))
            continue

        started = time.time()
        if args.source == "national":
            print(f"\n{year}: downloading the national CDL (~1.9 GB) ...")
            paths = [cdl.download_national_cdl(year, args.raster_dir)]
        else:
            print(f"\n{year}: downloading {len(states)} state rasters ...")
            fetched = cdl.download_many([year], states, args.raster_dir, pause=0.5)
            failures = {k: v for k, v in fetched.items() if isinstance(v, str)}
            if failures:
                print(f"  {len(failures)} failed: {list(failures)[:6]}")
            paths = [p for p in fetched.values() if not isinstance(p, str)]
        print(f"  {len(paths)} raster(s), {sum(p.stat().st_size for p in paths) / 1e9:.2f} GB, "
              f"{time.time() - started:.0f}s")

        print(f"  computing {len(geometry):,} cells ...")
        started = time.time()
        frame = cdl.forage_index(paths, geometry, radii_m=tuple(args.radii))
        frame.insert(4, "year", year)
        frame.to_csv(partial, index=False)
        frames.append(frame)

        primary = f"Forage_spring_{args.radii[0] // 1000}km"
        print(f"  {frame[primary].notna().sum():,}/{len(frame):,} scored, "
              f"mean {frame[primary].mean():.3f}, {time.time() - started:.0f}s")

        if args.discard_rasters:
            for path in paths:
                path.unlink(missing_ok=True)
            print("  rasters discarded")

    columns = ["lon", "lat", "col", "row", "year"] + [f"Forage_spring_{r // 1000}km"
                                                      for r in args.radii]
    table = pd.concat(frames, ignore_index=True)[columns]
    table.to_csv(out, index=False)

    # A year that lost state rasters still produces full-length rows -- the gaps
    # are NaN, not missing rows -- so say plainly which years are short.
    coverage = cdl.coverage_report(table, f"Forage_spring_{args.radii[0] // 1000}km")
    print("\ncoverage by year:")
    print(coverage.to_string())
    short = coverage.index[~coverage["complete"]].tolist()
    if short:
        print(f"\n*** INCOMPLETE YEARS: {short} ***")
        print("    State rasters failed to download for these. Delete the matching")
        print(f"    file(s) in {partial_dir} and rerun to fetch only those years.")
    primary = f"Forage_spring_{args.radii[0] // 1000}km"
    print(f"\nwrote {out}  ({len(table):,} cell-years)")
    print(f"  {primary}: {table[primary].notna().sum():,} populated, "
          f"range {table[primary].min():.3f}-{table[primary].max():.3f}")
    if table[primary].isna().any():
        print(f"  {table[primary].isna().sum():,} NaN (buffer outside all rasters) -- "
              "add the adjoining state to the mosaic if these matter")


if __name__ == "__main__":
    main()
