"""Tests for the dataset registry and file-configurable parameters.

These pin the contract the scripts rely on: a dataset knows where its inputs are,
refuses to half-run when they are absent, and works out its own usable years.
Nothing here needs the large weather matrices except where marked.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from applebee import datasets
from applebee.config import ModelParams

PA_AVAILABLE = datasets.DATASETS["pennsylvania"].available


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_covers_the_simulation_regions():
    assert set(datasets.DATASETS) == {"pennsylvania", "northeast", "conus"}


def test_new_york_is_deliberately_absent():
    # Its forage index is per site and per radius, not a (col, row, year) grid,
    # so it evaluates the egg-production sub-model rather than driving a run.
    assert "new_york" not in datasets.DATASETS


def test_unknown_dataset_lists_the_alternatives():
    with pytest.raises(KeyError, match="available"):
        datasets.get("massachusetts")


def test_every_dataset_declares_its_files():
    for name, d in datasets.DATASETS.items():
        paths = d.paths()
        assert "forage" in paths, name
        assert all(isinstance(p, Path) for p in paths.values()), name
        # matrices need three files per variable, a CSV needs one
        expected = 7 if d.form == datasets.MATRICES else 3
        assert len(paths) == expected, f"{name}: {sorted(paths)}"


def test_missing_inputs_raise_something_actionable(tmp_path):
    absent = datasets.Dataset(name="nowhere", weather_dir=tmp_path, form=datasets.MATRICES,
                              tmean="x_tmean", ppt="x_ppt", forage_csv=tmp_path/"none.csv")
    assert not absent.available
    assert len(absent.missing()) == 7
    with pytest.raises(FileNotFoundError, match="MANIFEST|fetch_prism"):
        absent.require()


def test_describe_handles_absent_datasets_without_loading(monkeypatch, tmp_path):
    monkeypatch.setitem(
        datasets.DATASETS, "phantom",
        datasets.Dataset(name="phantom", weather_dir=tmp_path, form=datasets.MATRICES,
                         tmean="a", ppt="b", forage_csv=tmp_path/"c.csv"),
    )
    frame = datasets.describe()
    row = frame[frame.dataset == "phantom"].iloc[0]
    assert row.available == False          # noqa: E712 -- pandas truthiness
    assert row.missing == 7


# ---------------------------------------------------------------------------
# Parameters from a file
# ---------------------------------------------------------------------------


def test_parameters_round_trip_through_json(tmp_path):
    original = ModelParams.calibrated()
    path = original.to_file(tmp_path / "p.json")
    assert ModelParams.from_file(path) == original


def test_a_config_need_only_name_what_it_changes(tmp_path):
    (tmp_path / "p.toml").write_text("temperature_threshold = 18.0\nlongevity = 24\n")
    params = ModelParams.from_file(tmp_path / "p.toml")
    assert params.temperature_threshold == 18.0
    assert params.longevity == 24
    assert params.precipitation_threshold == ModelParams().precipitation_threshold


def test_parameters_may_be_nested_under_a_table(tmp_path):
    (tmp_path / "p.toml").write_text("[parameters]\ntemperature_threshold = 15.5\n")
    assert ModelParams.from_file(tmp_path / "p.toml").temperature_threshold == 15.5


def test_a_typo_raises_rather_than_silently_using_the_default():
    # A misspelled key quietly running the literature value would be worse than
    # a stop: the run would look configured and would not be.
    with pytest.raises(ValueError, match="unknown parameter"):
        ModelParams.from_dict({"temprature_threshold": 18.0})
    with pytest.raises(TypeError, match="unknown parameter"):
        ModelParams().with_(tempreature_threshold=18.0)


def test_tuple_parameters_survive_serialisation(tmp_path):
    original = ModelParams().with_(prewinter_start=(8, 1))
    assert ModelParams.from_file(original.to_file(tmp_path / "p.json")).prewinter_start == (8, 1)


def test_differences_reports_only_what_changed():
    assert ModelParams().differences() == {}
    diff = ModelParams.calibrated().differences()
    assert set(diff) == {"forage_threshold", "temperature_threshold", "precipitation_threshold"}
    assert diff["temperature_threshold"] == (13.9, 18.72)


# ---------------------------------------------------------------------------
# Against the real Pennsylvania inputs
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PA_AVAILABLE, reason="Pennsylvania inputs absent")
def test_pennsylvania_reports_the_years_it_can_actually_run():
    # Weather runs 1990-2024 but forage only 2008-2023, and a year needs both.
    years = datasets.get("pennsylvania").weather_years()
    assert (years.start, years.stop - 1) == (2008, 2023)


@pytest.mark.skipif(not PA_AVAILABLE, reason="Pennsylvania inputs absent")
def test_cells_are_the_intersection_of_weather_and_forage():
    d = datasets.get("pennsylvania")
    tmean, _ = d.weather()
    weather_cells = {(int(c), int(r)) for c, r in zip(tmean.cells["col"], tmean.cells["row"])}
    cells = d.cells()
    assert cells, "no runnable cells"
    assert set(cells) <= weather_cells
    assert set(cells) <= set(d.forage().cells)


@pytest.mark.skipif(not PA_AVAILABLE, reason="Pennsylvania inputs absent")
def test_model_from_dataset_matches_the_hand_wired_model():
    # The registry must not change any answer -- this is the value the notebook,
    # the notes and the replication report all pin.
    result = datasets.get("pennsylvania").model().run_grid_year(1146, 240, 2018)
    assert result.eggs == 10
    assert result.emergence_doy == 128
    assert round(result.offspring, 3) == 8.850
