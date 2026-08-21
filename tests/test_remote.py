"""Tests for ranged reads and the file-configured region registry.

The point of the remote reader is that a hosted run should touch only the cells
it simulates, and should produce exactly what the local run produces. Both halves
are pinned here. Nothing needs a network: the reader takes a byte-range source,
and a local file is one.
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

from applebee import datasets
from applebee.remote import (FileRanges, RemoteMatrix, load_matrices_remote)
from applebee.weather import load_matrices


@pytest.fixture
def matrices(tmp_path):
    """A small three-cell, ten-day matrix set in the layout the loaders expect."""
    values = np.arange(30, dtype="float32").reshape(3, 10)
    np.save(tmp_path / "toy_tmean.values.npy", values)
    np.save(tmp_path / "toy_tmean.dates.npy",
            pd.date_range("2015-01-01", periods=10).values)
    pd.DataFrame({"col": [1, 2, 3], "row": [7, 7, 7],
                  "lon": [-77.0, -76.9, -76.8], "lat": [42.0, 42.0, 42.0]}
                 ).to_parquet(tmp_path / "toy_tmean.cells.parquet")
    return tmp_path, values


# ---------------------------------------------------------------------------
# RemoteMatrix
# ---------------------------------------------------------------------------


def test_reads_its_shape_and_dtype_from_the_file_header(matrices):
    path, values = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    assert m.shape == values.shape
    assert m.dtype == values.dtype
    assert len(m) == 3


def test_a_row_is_identical_to_the_stored_array(matrices):
    path, values = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    for i in range(len(values)):
        assert np.array_equal(m[i], values[i])
        assert np.array_equal(m[i, 2:6], values[i, 2:6])


def test_a_contiguous_row_block_is_one_read(matrices, monkeypatch):
    path, values = matrices
    ranges = FileRanges(path / "toy_tmean.values.npy")
    reads = []
    original = ranges.read
    monkeypatch.setattr(ranges, "read",
                        lambda o, n: (reads.append((o, n)), original(o, n))[1])
    m = RemoteMatrix(ranges)
    reads.clear()
    assert np.array_equal(m[np.array([0, 1, 2]), 0:10], values)
    assert len(reads) == 1, "a contiguous block should cost one request"


def test_row_cache_avoids_refetching(matrices, monkeypatch):
    path, _ = matrices
    ranges = FileRanges(path / "toy_tmean.values.npy")
    reads = []
    original = ranges.read
    monkeypatch.setattr(ranges, "read",
                        lambda o, n: (reads.append(o), original(o, n))[1])
    m = RemoteMatrix(ranges)
    reads.clear()
    for _ in range(5):
        m.row(1)
    assert len(reads) == 1


def test_refuses_a_layout_where_a_cell_is_not_contiguous(tmp_path):
    # Fortran order would put a cell's days far apart, so a "ranged" read would
    # quietly fetch the whole file. Better to refuse than to be slow in secret.
    np.save(tmp_path / "f.npy", np.asfortranarray(np.zeros((3, 4), dtype="float32")))
    with pytest.raises(ValueError, match="Fortran"):
        RemoteMatrix(FileRanges(tmp_path / "f.npy"))


def test_refuses_indexing_it_cannot_serve_faithfully(matrices):
    path, _ = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    with pytest.raises(TypeError, match="contiguous"):
        m[0, ::2]
    with pytest.raises(TypeError, match="RemoteMatrix"):
        m[0, 1, 2]


def test_a_block_outside_the_matrix_raises(matrices):
    path, _ = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    with pytest.raises(IndexError):
        m.read_rows(0, 99)


# ---------------------------------------------------------------------------
# The grid, and equivalence with the local loader
# ---------------------------------------------------------------------------


def test_remote_grid_matches_the_memory_mapped_one(matrices):
    path, _ = matrices
    local = load_matrices(path, "toy_tmean")
    remote = load_matrices_remote(path, "toy_tmean")
    assert remote.dates.equals(local.dates)
    assert remote.cells.equals(local.cells)
    assert remote.n_cells == local.n_cells
    assert np.array_equal(remote.series(1, 7, "2015-01-03", 4),
                          local.series(1, 7, "2015-01-03", 4))


# ---------------------------------------------------------------------------
# Registry as data
# ---------------------------------------------------------------------------


def test_the_shipped_registry_still_defines_the_three_regions():
    registry = datasets.load_registry(datasets.REGIONS_JSON)
    assert set(registry) == {"pennsylvania", "northeast", "conus"}
    assert registry["northeast"].forage_csv.is_absolute()


def test_an_unknown_key_in_a_region_file_raises(tmp_path):
    bad = tmp_path / "regions.json"
    bad.write_text(json.dumps({"maine": {"tmean": "t", "ppt": "p",
                                         "forage_csv": "f.csv", "resolution": "4km"}}))
    with pytest.raises(ValueError, match="resolution"):
        datasets.load_registry(bad)


def test_a_remote_region_needs_nothing_on_this_disk(tmp_path):
    remote = tmp_path / "regions.json"
    remote.write_text(json.dumps({"northeast_s3": {
        "base_url": "https://example.invalid/weather/northeast",
        "tmean": "northeast_tmean", "ppt": "northeast_ppt",
        "forage_csv": "https://example.invalid/forage/northeast.csv",
        "description": "hosted"}}))
    dataset = datasets.load_registry(remote)["northeast_s3"]
    assert dataset.base_url and dataset.paths() == {}
    assert dataset.available          # nothing local to be missing
    dataset.require()                 # and so nothing to refuse
    assert dataset.forage_csv.startswith("https://")


def test_a_region_file_extends_the_registry(tmp_path, monkeypatch):
    extra = tmp_path / "regions.json"
    extra.write_text(json.dumps({"toy": {"weather_dir": "weather/toy",
                                         "tmean": "toy_tmean", "ppt": "toy_ppt",
                                         "forage_csv": "forage/toy.csv"}}))
    monkeypatch.setenv(datasets.REGIONS_ENV, str(extra))
    registry = dict(datasets.load_registry(datasets.REGIONS_JSON))
    registry.update(datasets.load_registry(os.environ[datasets.REGIONS_ENV]))
    assert "toy" in registry and "northeast" in registry


def test_a_matrix_replaced_underneath_is_noticed(matrices):
    """The worker rewrites these files when it extends them. A reader holding
    the old stride would index the new file wrongly and return bytes from the
    middle of another row -- plausible rubbish rather than an error."""
    path, values = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    assert m.shape == (3, 10)
    assert np.array_equal(m[1], values[1])

    grown = np.arange(60, dtype="float32").reshape(3, 20)
    np.save(path / "toy_tmean.values.npy", grown)

    assert m.reread_if_replaced(every_seconds=0) is True
    assert m.shape == (3, 20)
    assert np.array_equal(m[1], grown[1])
    assert m.reread_if_replaced(every_seconds=0) is False


def test_the_check_is_throttled(matrices):
    path, _ = matrices
    m = RemoteMatrix(FileRanges(path / "toy_tmean.values.npy"))
    # The first check always runs -- a process that has just started should not
    # trust a header it has never verified.
    assert m.reread_if_replaced(every_seconds=3600) is False
    np.save(path / "toy_tmean.values.npy", np.zeros((3, 20), dtype="float32"))
    # After that it is throttled: a matrix changes a few times a year, and a
    # request should not pay for a HEAD on every call.
    assert m.reread_if_replaced(every_seconds=3600) is False
    assert m.shape == (3, 10)
    assert m.reread_if_replaced(every_seconds=0) is True
