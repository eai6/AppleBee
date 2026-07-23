"""Objective 2: Sobol sensitivity of egg-production performance to its thresholds.

Varies the forage, temperature and precipitation thresholds over the ranges in
Table 4-5, re-evaluates the egg-production sub-model against Centrella et al.
(2020) for each combination, and decomposes the variance in R^2.
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from SALib.analyze import sobol as sobol_analyze
from SALib.sample import sobol as sobol_sample

from applebee.config import FIGURES, SOBOL_PROBLEM, TABLES, ModelParams
from applebee.evaluation.centrella import (
    build_design,
    fit_lme,
    load_centrella,
    r2_and_rmse,
)

SERIES_BLUE = "#2a78d6"
TEXT_SECONDARY = "#52514e"


def evaluate_r2(data, forage_t: float, temp_t: float, precip_t: float) -> float:
    params = ModelParams(
        forage_threshold=forage_t,
        temperature_threshold=temp_t,
        precipitation_threshold=precip_t,
    )
    try:
        design = build_design(data, params)
        fit = fit_lme(design)
        r2, _ = r2_and_rmse(design["observed_eggs"], fit.fittedvalues)
        return r2
    except Exception:
        return np.nan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # Saltelli sampling yields N * (2D + 2) evaluations; N=128 -> 1024, matching
    # the ~1000 combinations the chapter reports.
    parser.add_argument("--n", type=int, default=128, help="Saltelli base sample size")
    args = parser.parse_args()

    data = load_centrella()
    samples = sobol_sample.sample(SOBOL_PROBLEM, args.n, calc_second_order=False)
    print(f"evaluating {len(samples):,} threshold combinations...", flush=True)

    start = time.time()
    scores = np.empty(len(samples))
    for i, (forage_t, temp_t, precip_t) in enumerate(samples):
        scores[i] = evaluate_r2(data, forage_t, temp_t, precip_t)
        if (i + 1) % 200 == 0:
            print(f"  {i+1:,}/{len(samples):,}", flush=True)
    print(f"done in {time.time()-start:.0f}s")

    valid = ~np.isnan(scores)
    if not valid.all():
        print(f"  {(~valid).sum()} evaluations failed; filling with the mean")
        scores[~valid] = np.nanmean(scores)

    indices = sobol_analyze.analyze(SOBOL_PROBLEM, scores, calc_second_order=False)
    table = pd.DataFrame(
        {
            "parameter": SOBOL_PROBLEM["names"],
            "S1": indices["S1"],
            "S1_conf": indices["S1_conf"],
            "ST": indices["ST"],
            "ST_conf": indices["ST_conf"],
        }
    )
    TABLES.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLES / "objective2_sobol.csv", index=False)

    print("\n=== Sobol indices (chapter: precipitation S1 0.38 / ST 0.46;")
    print("    forage 0.30 / 0.37; temperature 0.18 / 0.33) ===")
    print(table.round(3).to_string(index=False))

    best = int(np.argmax(scores))
    print(
        f"\nbest R^2 = {scores[best]:.3f} at forage={samples[best][0]:.3f}, "
        f"temperature={samples[best][1]:.2f} degC, precipitation={samples[best][2]:.2f} mm"
    )
    print("  (chapter: R^2 0.60 at forage 0.54, temperature 18.72 degC, precipitation 4.33 mm)")

    sampled = pd.DataFrame(samples, columns=SOBOL_PROBLEM["names"])
    sampled["r2"] = scores
    sampled.to_csv(TABLES / "objective2_sobol_samples.csv", index=False)

    _plot(table, sampled)


def _plot(table: pd.DataFrame, sampled: pd.DataFrame) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    labels = {
        "forage_threshold": "Forage threshold",
        "temperature_threshold": "Temperature threshold",
        "precipitation_threshold": "Precipitation threshold",
    }

    # Figure 4-5: first-order vs total sensitivity.
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(table))
    width = 0.38
    ax.bar(x - width / 2, table["S1"], width, color=SERIES_BLUE, label="First-order")
    ax.bar(x + width / 2, table["ST"], width, color="#9dbfe8", label="Total")
    for xi, (s1, st) in enumerate(zip(table["S1"], table["ST"])):
        ax.text(xi - width / 2, s1 + 0.01, f"{s1:.2f}", ha="center", fontsize=8, color=TEXT_SECONDARY)
        ax.text(xi + width / 2, st + 0.01, f"{st:.2f}", ha="center", fontsize=8, color=TEXT_SECONDARY)
    ax.set_xticks(x)
    ax.set_xticklabels([labels[n] for n in table["parameter"]], fontsize=8)
    ax.set_ylabel("Sensitivity index")
    ax.set_title("Sobol sensitivity of egg-production performance", fontsize=11)
    ax.legend(frameon=False)
    fig.savefig(FIGURES / "figure_4_05_sobol.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 4-6: R^2 against each threshold, plus its distribution.
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.5))
    axes[0, 0].hist(sampled["r2"], bins=25, color=SERIES_BLUE)
    axes[0, 0].set_xlabel("$R^2$ values")
    axes[0, 0].set_ylabel("Frequency")
    for ax, name in zip(axes.ravel()[1:], SOBOL_PROBLEM["names"]):
        ax.scatter(sampled[name], sampled["r2"], s=4, color=SERIES_BLUE, alpha=0.45, linewidths=0)
        ax.set_xlabel(labels[name])
        ax.set_ylabel("$R^2$")
    fig.suptitle("Egg-production performance across sampled thresholds", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_4_06_sobol_scatter.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
