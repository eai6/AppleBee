"""Objective 4 analysis: spatio-temporal trends, driver importance, no-egg days.

Reproduces the analyses reported in the chapter's Objective 4 results:

* summary statistics of offspring per female across Pennsylvania;
* a random-forest regression ranking the four sub-models as predictors of
  offspring (Figure 4-13);
* a one-tailed t-test comparing no-egg days caused by temperature against
  those caused by precipitation (Figure 4-14).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from applebee.config import OUTPUTS, TABLES

RANDOM_SEED = 0

FEATURES = {
    "emergence_doy": "Julian Emergence Date",
    "eggs": "Egg Production",
    "egg_larva_mortality": "Egg and Larva Mortality",
    "winter_mortality": "Winter Mortality",
}


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """Statewide and per-grid summaries of offspring per female."""
    per_grid_sd = results.groupby(["col", "row"])["offspring"].std()
    lines = {
        "offspring_max": results["offspring"].max(),
        "offspring_mean": results["offspring"].mean(),
        "offspring_min": results["offspring"].min(),
        "per_grid_sd_max": per_grid_sd.max(),
        "per_grid_sd_mean": per_grid_sd.mean(),
        "per_grid_sd_min": per_grid_sd.min(),
    }
    return pd.DataFrame({"statistic": list(lines), "value": np.round(list(lines.values()), 2)})


def feature_importance(results: pd.DataFrame) -> pd.DataFrame:
    """Random forest over the four sub-model outputs (Figure 4-13)."""
    X = results[list(FEATURES)].to_numpy(dtype=float)
    y = results["offspring"].to_numpy(dtype=float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED
    )
    scaler = StandardScaler().fit(X_train)
    forest = RandomForestRegressor(n_estimators=100, random_state=RANDOM_SEED, n_jobs=-1)
    forest.fit(scaler.transform(X_train), y_train)

    frame = pd.DataFrame(
        {
            "feature": [FEATURES[f] for f in FEATURES],
            "importance": forest.feature_importances_,
        }
    ).sort_values("importance", ascending=False)
    frame["importance_pct"] = (frame["importance"] * 100).round(3)
    frame.attrs["test_r2"] = forest.score(scaler.transform(X_test), y_test)
    return frame


def no_egg_day_test(results: pd.DataFrame) -> dict:
    """One-tailed t-test: temperature-limited vs precipitation-limited days."""
    temperature = results["no_egg_days_temperature"].to_numpy(dtype=float)
    precipitation = results["no_egg_days_precipitation"].to_numpy(dtype=float)
    # Welch's t-test; the alternative is that temperature limits more days.
    result = stats.ttest_ind(temperature, precipitation, equal_var=False, alternative="greater")
    return {
        "temperature_mean": temperature.mean(),
        "temperature_sd": temperature.std(ddof=1),
        "precipitation_mean": precipitation.mean(),
        "precipitation_sd": precipitation.std(ddof=1),
        "t_statistic": result.statistic,
        "df": result.df,
        "p_value": result.pvalue,
    }


def main() -> None:
    path = OUTPUTS / "pa_simulation_default.parquet"
    results = pd.read_parquet(path)
    TABLES.mkdir(parents=True, exist_ok=True)

    print(f"loaded {len(results):,} cell-years from {path.name}\n")

    print("=== Summary statistics (chapter: max 30, mean 17, min 1;")
    print("    per-grid SD max 9, mean 5, min 2) ===")
    summary = summarise(results)
    print(summary.to_string(index=False))
    summary.to_csv(TABLES / "objective4_summary.csv", index=False)

    print("\n=== Offspring per female by year ===")
    by_year = results.groupby("offspring_year")["offspring"].agg(["mean", "std", "min", "max"])
    print(by_year.round(2).to_string())
    by_year.round(3).to_csv(TABLES / "objective4_by_year.csv")

    print("\n=== Random forest feature importance (chapter: egg production 98.348%,")
    print("    egg+larva mortality 1.596%, winter mortality 0.054%, emergence 0.002%) ===")
    importance = feature_importance(results)
    print(importance.to_string(index=False))
    print(f"  test R^2 = {importance.attrs['test_r2']:.4f}")
    importance.to_csv(TABLES / "objective4_feature_importance.csv", index=False)

    print("\n=== No-egg days (chapter: temperature 6.38+/-3.82 vs precipitation")
    print("    4.40+/-1.97, t=158.23, p=0.00) ===")
    test = no_egg_day_test(results)
    for key, value in test.items():
        print(f"  {key:22s} {value:,.4f}")
    pd.DataFrame([test]).to_csv(TABLES / "objective4_no_egg_days.csv", index=False)


if __name__ == "__main__":
    main()
