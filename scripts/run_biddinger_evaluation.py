"""Objective 3b: evaluate AppleBee against the Biddinger Osmia database.

Rebuilds the chapter's Objective 3 on a panel that can actually support it --
cell-years rather than six annual counts at one site, with the random intercept
on cell (many years per group) rather than year (one observation per group).

Reports marginal R^2 alongside conditional R^2 everywhere. Quoting only the
conditional value is what made the chapter's 0.79 look convincing; see section 2
of docs/REPLICATION_NOTES.md.

    .venv/bin/python scripts/run_biddinger_evaluation.py

Writes outputs/tables/objective3b_*.csv.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee import AppleBee, ForageGrid, ModelParams, load_weather  # noqa: E402
from applebee.config import (  # noqa: E402
    PA_FORAGE_CSV,
    PA_PPT_CSV,
    PA_TMEAN_CSV,
    TABLES,
)
from applebee.evaluation import biddinger as B  # noqa: E402
from applebee.evaluation import turley as T  # noqa: E402

warnings.filterwarnings("ignore")

# Species order is deliberate: genus first, so the headline number is directly
# comparable with the chapter, then cornifrons alone as the sharper test of a
# model parameterised for that species.
SPECIES_VARIANTS = (("Osmia genus", None), ("O. cornifrons", "cornifrons"))


def main() -> None:
    tmean = load_weather(PA_TMEAN_CSV, "pa_tmean")
    ppt = load_weather(PA_PPT_CSV, "pa_ppt")
    model = AppleBee(tmean, ppt, ForageGrid.load(PA_FORAGE_CSV), ModelParams())

    data = B.load_specimens()
    specimens = B.assign_cells(data.specimens, tmean.cells)
    print(
        f"Biddinger: {data.dropped['kept']} usable specimens "
        f"({data.dropped['no_usable_location_or_year']} dropped for missing "
        f"location or year); {data.n_shared} IDs shared with Turley, "
        f"{data.n_turley_only} Turley-only records merged in."
    )
    print(f"{specimens[['col', 'row']].drop_duplicates().shape[0]} PRISM cells.\n")

    # -- headline: the primary panel, both responses ------------------------
    headline = []
    for label, species in SPECIES_VARIANTS:
        result = B.evaluate(model, B.build_panel(specimens, species=species))
        headline.append(
            {
                "response": label,
                "n": result["n"],
                "cells": result["n_cells"],
                "marginal_r2": round(result["marginal_r2"], 4),
                "conditional_r2": round(result["conditional_r2"], 4),
                "slope": round(result["slope"], 3),
                "slope_p": round(result["slope_p"], 4),
                "rmse": round(result["rmse"], 2),
            }
        )

    # The chapter's own evaluation, decomposed the same way.
    turley = T.evaluate(model)
    design, fit = turley["design"], turley["fit"]
    fixed = fit.params["Intercept"] + fit.params["predicted"] * design["predicted"]
    observed = design["observed"].to_numpy(float)
    ss_tot = float(((observed - observed.mean()) ** 2).sum())
    headline.append(
        {
            "response": "Turley 2014-2019 (chapter Objective 3)",
            "n": len(design),
            "cells": 1,
            "marginal_r2": round(1 - float(((observed - fixed) ** 2).sum()) / ss_tot, 4),
            "conditional_r2": round(turley["r2"], 4),
            "slope": round(float(fit.params["predicted"]), 3),
            "slope_p": round(float(fit.pvalues["predicted"]), 4),
            "rmse": round(turley["rmse"], 2),
        }
    )
    headline = pd.DataFrame(headline)
    print("=== Objective 3b, primary panel (blue vane, 3 continuously sampled cells) ===")
    print(headline.to_string(index=False), "\n")

    # -- sensitivity: does the result depend on the restriction choices? ----
    grid = []
    for label, species in SPECIES_VARIANTS:
        for cell_label, cells in (
            ("3 continuous", B.CONTINUOUS_CELLS),
            ("all sampled cells", None),
        ):
            for zero_label, drop in (("drop ambiguous", True), ("keep as zero", False)):
                result = B.evaluate(
                    model,
                    B.build_panel(
                        specimens,
                        species=species,
                        cells=cells,
                        drop_ambiguous_zeros=drop,
                    ),
                )
                grid.append(
                    {
                        "response": label,
                        "cells": cell_label,
                        "zeros": zero_label,
                        "n": result["n"],
                        "n_cells": result["n_cells"],
                        "marginal_r2": round(result["marginal_r2"], 4),
                        "conditional_r2": round(result["conditional_r2"], 4),
                        "slope": round(result["slope"], 3),
                        "slope_p": round(result["slope_p"], 4),
                    }
                )
    grid = pd.DataFrame(grid)
    print("=== sensitivity to the restriction choices ===")
    print(grid.to_string(index=False), "\n")

    # -- the Turley site alone, 6 years against 13 --------------------------
    site = B.build_design(model, B.build_panel(specimens, cells=((1146, 240),)))
    print("=== Turley's own cell (1146, 240), extended from 6 years to 13 ===")
    print(site[["year", "observed", "predicted"]].to_string(index=False), "\n")

    TABLES.mkdir(parents=True, exist_ok=True)
    headline.to_csv(TABLES / "objective3b_headline.csv", index=False)
    grid.to_csv(TABLES / "objective3b_sensitivity.csv", index=False)
    site.to_csv(TABLES / "objective3b_turley_cell_extended.csv", index=False)
    print(f"wrote objective3b_*.csv to {TABLES}")


if __name__ == "__main__":
    main()
