"""Render the AppleBee replication figures.

Reproduces Figures 4-11 to 4-14 (Objective 4) plus the evaluation figures for
Objectives 2 and 3. Sequential magnitude (offspring per female) uses a single
blue hue light-to-dark; the one categorical comparison (no-egg days by driver)
uses a validated blue/orange pair.
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from applebee.config import FIGURES, OUTPUTS, PA_TMEAN_CSV
from applebee.weather import load_weather

# --- shared style ---------------------------------------------------------
# Recessive axes and grid; text in ink, never in a series colour.
SERIES_BLUE = "#2a78d6"
SERIES_ORANGE = "#eb6834"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#d8d7d2"

mpl.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 9,
        "text.color": TEXT_PRIMARY,
        "axes.labelcolor": TEXT_PRIMARY,
        "axes.edgecolor": TEXT_SECONDARY,
        "axes.linewidth": 0.8,
        "axes.grid": False,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

CELL_DEG = 1.0 / 24.0  # PRISM 4 km grid spacing in degrees


def with_coordinates(results: pd.DataFrame) -> pd.DataFrame:
    """Attach cell centroid lon/lat to simulation output."""
    cells = load_weather(PA_TMEAN_CSV, "pa_tmean").cells[["col", "row", "lon", "lat"]]
    return results.merge(cells, on=["col", "row"], how="left")


def _draw_map(ax, frame: pd.DataFrame, value: str, vmin: float, vmax: float):
    """Render the regular 4 km grid as a raster, coloured by magnitude.

    The cells form a complete lattice in (col, row), so pivoting to a 2-D array
    and drawing it with imshow gives gapless cells -- a scatter of square
    markers leaves seams that read as missing data.
    """
    grid = frame.pivot_table(index="row", columns="col", values=value, aggfunc="mean")
    # PRISM row numbers increase southward, so the array is already top-down.
    lon = frame["lon"].to_numpy()
    lat = frame["lat"].to_numpy()
    extent = [
        lon.min() - CELL_DEG / 2,
        lon.max() + CELL_DEG / 2,
        lat.min() - CELL_DEG / 2,
        lat.max() + CELL_DEG / 2,
    ]
    return ax.imshow(
        grid.to_numpy(),
        cmap="Blues",
        vmin=vmin,
        vmax=vmax,
        extent=extent,
        origin="upper",
        interpolation="nearest",
        aspect="equal",
    )


def figure_4_11(results: pd.DataFrame) -> None:
    """Spatial distribution of predicted adult offspring per female, by year."""
    years = sorted(results["offspring_year"].unique())
    ncols = 4
    nrows = int(np.ceil(len(years) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 2.3 * nrows), constrained_layout=True)
    vmin, vmax = 0, 35

    for ax, year in zip(axes.ravel(), years):
        frame = results[results["offspring_year"] == year]
        mappable = _draw_map(ax, frame, "offspring", vmin, vmax)
        ax.set_title(str(year), fontsize=9)
        ax.set_aspect("equal")
        ax.tick_params(labelsize=6)
    for ax in axes.ravel()[len(years) :]:
        ax.axis("off")

    bar = fig.colorbar(mappable, ax=axes, shrink=0.6, pad=0.01)
    bar.set_label("Adult offspring per female", fontsize=8)
    fig.suptitle(
        "Predicted adult offspring per female across Pennsylvania, 2009-2024",
        fontsize=11,
    )
    fig.savefig(FIGURES / "figure_4_11_offspring_by_year.png")
    plt.close(fig)


def figure_4_12(results: pd.DataFrame) -> None:
    """Average predicted offspring per female over the full period."""
    mean = results.groupby(["col", "row"], as_index=False).agg(
        offspring=("offspring", "mean"), lon=("lon", "first"), lat=("lat", "first")
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    mappable = _draw_map(ax, mean, "offspring", 0, 25)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Average predicted adult offspring per female, 2009-2024", fontsize=11)
    bar = fig.colorbar(mappable, ax=ax, shrink=0.85)
    bar.set_label("Average adult offspring per female", fontsize=8)
    fig.savefig(FIGURES / "figure_4_12_offspring_average.png")
    plt.close(fig)


def figure_4_13(importance: pd.DataFrame) -> None:
    """Random-forest importance of each sub-model for predicting offspring."""
    frame = importance.sort_values("importance")
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.barh(frame["feature"], frame["importance"], color=SERIES_BLUE, height=0.6)
    # Direct-label the bars; a single series needs no legend.
    for y, (value, pct) in enumerate(zip(frame["importance"], frame["importance_pct"])):
        ax.text(value + 0.012, y, f"{pct:.3f}%", va="center", fontsize=8, color=TEXT_SECONDARY)
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("Importance (mean decrease in impurity)")
    ax.set_title("Egg production dominates predicted reproductive success", fontsize=11)
    fig.savefig(FIGURES / "figure_4_13_feature_importance.png")
    plt.close(fig)


def figure_4_14(results: pd.DataFrame) -> None:
    """No-egg days attributable to temperature versus precipitation, by year."""
    years = sorted(results["offspring_year"].unique())
    fig, ax = plt.subplots(figsize=(11, 4))
    width = 0.38

    for offset, column, colour, label in [
        (-width / 2, "no_egg_days_precipitation", SERIES_BLUE, "Precipitation"),
        (width / 2, "no_egg_days_temperature", SERIES_ORANGE, "Temperature"),
    ]:
        data = [results.loc[results["offspring_year"] == y, column].to_numpy() for y in years]
        ax.boxplot(
            data,
            positions=np.arange(len(years)) + offset,
            widths=width * 0.9,
            patch_artist=True,
            showfliers=False,
            boxprops={"facecolor": colour, "edgecolor": TEXT_SECONDARY, "linewidth": 0.6},
            medianprops={"color": "white", "linewidth": 1.2},
            whiskerprops={"color": TEXT_SECONDARY, "linewidth": 0.6},
            capprops={"color": TEXT_SECONDARY, "linewidth": 0.6},
        )
        ax.plot([], [], color=colour, linewidth=6, label=label)

    ax.set_xticks(np.arange(len(years)))
    ax.set_xticklabels(years, rotation=45, fontsize=8)
    ax.set_xlabel("Year")
    ax.set_ylabel("No-egg days")
    ax.set_title("Days when egg laying was blocked, by limiting driver", fontsize=11)
    ax.legend(frameon=False, loc="upper right")
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    fig.savefig(FIGURES / "figure_4_14_no_egg_days.png")
    plt.close(fig)


def _scatter_fit(ax, observed, predicted, xlabel, ylabel, r2, rmse):
    ax.scatter(predicted, observed, color=SERIES_BLUE, s=34, alpha=0.75, linewidths=0)
    slope, intercept = np.polyfit(predicted, observed, 1)
    xs = np.linspace(min(predicted), max(predicted), 100)
    ax.plot(xs, slope * xs + intercept, color=TEXT_PRIMARY, linewidth=1.6)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.text(
        0.04,
        0.95,
        f"$R^2$ = {r2:.2f}\nRMSE = {rmse:.2f}",
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        color=TEXT_SECONDARY,
    )


def figure_evaluations() -> None:
    """Objective 2 and Objective 3 evaluation figures (chapter Figs 4-3, 4-7)."""
    from applebee import AppleBee, ForageGrid, ModelParams, load_weather as _lw
    from applebee.config import PA_FORAGE_CSV, PA_PPT_CSV
    from applebee.evaluation import centrella, turley

    # --- Objective 2: egg production on Centrella et al. (2020) ---
    data = centrella.load_centrella()
    result = centrella.evaluate(ModelParams(), data)
    design = result["design"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    _scatter_fit(
        ax,
        design["observed_eggs"].to_numpy(float),
        result["fit"].fittedvalues.to_numpy(float),
        "Predicted (eggs/site)",
        "Observed (eggs/site)",
        result["r2"],
        result["rmse"],
    )
    ax.set_title("Egg production sub-model\n(Centrella et al. 2020, n=51)", fontsize=10)
    fig.savefig(FIGURES / "figure_4_03_egg_production_evaluation.png")
    plt.close(fig)

    # --- Objective 3: full model on Turley et al. (2022) ---
    model = AppleBee(
        _lw(PA_TMEAN_CSV, "pa_tmean"),
        _lw(PA_PPT_CSV, "pa_ppt"),
        ForageGrid.load(PA_FORAGE_CSV),
        ModelParams(),
    )
    evaluation = turley.evaluate(model)
    design = evaluation["design"]
    fitted = evaluation["fit"].fittedvalues.to_numpy(float)

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))
    _scatter_fit(
        axes[0],
        design["observed"].to_numpy(float),
        fitted,
        "Predicted (No. bees/year)",
        "Observed (No. bees/year)",
        evaluation["r2"],
        evaluation["rmse"],
    )
    axes[1].plot(
        design["year"], design["observed"], marker="o", color=TEXT_SECONDARY, label="Observed"
    )
    axes[1].plot(design["year"], fitted, marker="x", color=SERIES_BLUE, label="Predicted")
    axes[1].set_xlabel("Year")
    axes[1].set_ylabel("Osmia abundance (No. bees/year)")
    axes[1].legend(frameon=False)
    axes[1].yaxis.grid(True, color=GRID, linewidth=0.6)
    axes[1].set_axisbelow(True)
    fig.suptitle("AppleBee model vs Osmia monitoring, Adams County PA", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_4_07_applebee_evaluation.png")
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    results = with_coordinates(pd.read_parquet(OUTPUTS / "pa_simulation_default.parquet"))

    from analyse_pa_simulation import feature_importance

    print("figure 4-11 (offspring by year)...", flush=True)
    figure_4_11(results)
    print("figure 4-12 (period average)...", flush=True)
    figure_4_12(results)
    print("figure 4-13 (feature importance)...", flush=True)
    figure_4_13(feature_importance(results))
    print("figure 4-14 (no-egg days)...", flush=True)
    figure_4_14(results)
    print("evaluation figures...", flush=True)
    figure_evaluations()
    print(f"\nwritten to {FIGURES}")
    for path in sorted(FIGURES.glob("*.png")):
        print(f"  {path.name}  ({path.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
