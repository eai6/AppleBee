"""Tests for the data-acquisition pipelines.

The grid tests are pure arithmetic and always run. The CDL test needs the
archived Pennsylvania raster and the geospatial extras, and is skipped without
them -- it is the regression check that the local forage pipeline still
reproduces the archived ``forage.csv``.

No test here makes a network request. PRISM allows only two downloads of a file
per 24 hours and blocks IPs for excessive activity, so a test suite must never
hit it.
"""

import numpy as np
import pandas as pd
import pytest

from applebee.acquire import grid

pytest_plugins: list[str] = []

FORAGE_CSV = grid.__file__.rsplit("applebee", 1)[0] + "archives/data/forage.csv"
CDL_2021 = (
    grid.__file__.rsplit("applebee", 1)[0]
    + "archives/data/CDL/pennsylvania/CDL_2021_STATE_FIPS_42.tif"
)


# ---------------------------------------------------------------------------
# The PRISM 4 km grid
# ---------------------------------------------------------------------------


def test_grid_matches_the_archived_pennsylvania_indices():
    # The whole pipeline keys on (col, row); if this drifts, newly acquired data
    # silently stops lining up with the existing Pennsylvania inputs.
    assert int(grid.col_of(-79.875)) == 1083
    assert int(grid.row_of(42.25)) == 184


def test_cell_centres_round_trip():
    for col, row in [(1083, 184), (1146, 240), (0, 0), (1404, 620)]:
        assert int(grid.col_of(grid.lon_of(col))) == col
        assert int(grid.row_of(grid.lat_of(row))) == row


@pytest.mark.skipif(not __import__("os").path.exists(FORAGE_CSV), reason="archived forage.csv absent")
def test_every_archived_pennsylvania_cell_reproduces():
    cells = pd.read_csv(FORAGE_CSV, usecols=["col", "row", "lon", "lat"]).drop_duplicates()
    assert (grid.col_of(cells.lon.to_numpy()) == cells.col.to_numpy()).all()
    assert (grid.row_of(cells.lat.to_numpy()) == cells.row.to_numpy()).all()
    assert np.abs(grid.lon_of(cells.col.to_numpy()) - cells.lon.to_numpy()).max() < 1e-6
    assert np.abs(grid.lat_of(cells.row.to_numpy()) - cells.lat.to_numpy()).max() < 1e-6


def test_bbox_selection_is_bounded_and_ordered():
    cells = grid.cells_in_bbox((-80.6, 39.6, -74.6, 42.4))
    assert len(cells) > 5000
    assert cells.lon.between(-80.6, -74.6).all()
    assert cells.lat.between(39.6, 42.4).all()
    assert cells[["row", "col"]].apply(tuple, axis=1).is_monotonic_increasing


def test_bbox_is_validated():
    with pytest.raises(ValueError, match="west<east"):
        grid.cells_in_bbox((-74.0, 39.0, -80.0, 42.0))
    with pytest.raises(ValueError, match="does not overlap"):
        grid.cells_in_bbox((-179.0, 5.0, -178.0, 6.0))


def test_northeast_region_is_larger_than_pennsylvania():
    assert len(grid.NORTHEAST.cells()) > 10 * len(grid.PENNSYLVANIA.cells()) / 2
    assert "PA" in grid.NORTHEAST.states


# ---------------------------------------------------------------------------
# CDL -> forage index
# ---------------------------------------------------------------------------


def _skip_without_geo():
    pytest.importorskip("rasterio")
    pytest.importorskip("exactextract")
    pytest.importorskip("geopandas")


def test_koh_lookup_covers_the_documented_range():
    _skip_without_geo()
    from applebee.acquire import cdl

    lookup = cdl.load_koh_lookup()
    assert lookup.shape == (256,)
    assert lookup[0] == 0.0                      # class 0 is Background
    assert 0.6 < lookup.max() <= 1.0
    assert (lookup >= 0).all()


@pytest.mark.skipif(not __import__("os").path.exists(CDL_2021), reason="archived CDL raster absent")
def test_forage_pipeline_reproduces_the_archived_index():
    # The regression check for the whole CDL -> forage method. Reported in
    # memory/4: r = 0.985 (1 km), 0.990 (3 km), 0.992 (5 km) on this sample.
    _skip_without_geo()
    from applebee.acquire import cdl

    truth = pd.read_csv(FORAGE_CSV).query("year == 2021")
    sample = truth.sample(25, random_state=0).reset_index(drop=True)
    got = cdl.forage_index(CDL_2021, sample[["col", "row", "lon", "lat"]])

    for radius in (1, 3, 5):
        column = f"Forage_spring_{radius}km"
        usable = got[column].notna()
        assert usable.sum() >= 20, f"too many empty buffers at {radius} km"
        expected = sample.loc[usable, column].to_numpy()
        actual = got.loc[usable, column].to_numpy()
        assert np.corrcoef(expected, actual)[0, 1] > 0.95
        assert np.abs(expected - actual).mean() < 0.05


@pytest.mark.skipif(not __import__("os").path.exists(CDL_2021), reason="archived CDL raster absent")
def test_buffers_outside_the_raster_are_nan_not_zero():
    # A buffer beyond the state-clipped raster must not silently score 0, which
    # would read as "no floral resources" instead of "no data".
    _skip_without_geo()
    from applebee.acquire import cdl

    far = pd.DataFrame({"col": [1], "row": [1], "lon": [-124.0], "lat": [48.0]})
    got = cdl.forage_index(CDL_2021, far)
    assert np.isnan(got["Forage_spring_1km"].iloc[0])


# ---------------------------------------------------------------------------
# PRISM -- offline behaviour only
# ---------------------------------------------------------------------------


def test_prism_estimate_makes_no_request(tmp_path):
    from applebee.acquire import prism

    report = prism.estimate(tmp_path, ("tmean", "ppt"), "2020-01-01", "2020-01-10")
    assert report["variable_days_total"] == 20
    assert report["to_download"] == 20
    assert report["already_held"] == 0
    assert report["approx_GB"] > 0


def test_prism_rejects_unknown_variables(tmp_path):
    from applebee.acquire import prism

    with pytest.raises(ValueError, match="variable must be one of"):
        prism.download_day(tmp_path, "humidity", "2020-01-01")


def test_prism_pause_default_is_conservative():
    # PRISM blocks IPs for excessive activity; a short default would invite it.
    from applebee.acquire import prism

    assert prism.DEFAULT_PAUSE_SECONDS >= 2.0
    assert issubclass(prism.RateLimited, RuntimeError)


@pytest.mark.skipif(not __import__("os").path.exists(CDL_2021), reason="archived CDL raster absent")
def test_background_handling_does_not_disturb_interior_cells():
    # CDL class 0 is "Background" -- outside the state line, or ocean. Treating it
    # as no-data rescues border cells without moving interior ones, so the
    # Pennsylvania validation must be identical either way.
    _skip_without_geo()
    from applebee.acquire import cdl

    sample = pd.read_csv(FORAGE_CSV).query("year == 2021").sample(15, random_state=0)
    cells = sample[["col", "row", "lon", "lat"]].reset_index(drop=True)
    scored = cdl.forage_index(CDL_2021, cells, background_as_nodata=False)
    renormalised = cdl.forage_index(CDL_2021, cells, background_as_nodata=True)

    both = scored["Forage_spring_3km"].notna() & renormalised["Forage_spring_3km"].notna()
    assert both.sum() >= 12
    difference = (scored.loc[both, "Forage_spring_3km"]
                  - renormalised.loc[both, "Forage_spring_3km"]).abs()
    assert difference.max() < 0.02, "interior cells should not move"


@pytest.mark.skipif(not __import__("os").path.exists(CDL_2021), reason="archived CDL raster absent")
def test_all_background_buffer_is_nan_not_zero():
    _skip_without_geo()
    from applebee.acquire import cdl

    # Far offshore: inside the raster envelope but entirely Background.
    offshore = pd.DataFrame({"col": [1], "row": [1], "lon": [-74.2], "lat": [39.0]})
    got = cdl.forage_index(CDL_2021, offshore, radii_m=(1000,), background_as_nodata=True)
    assert np.isnan(got["Forage_spring_1km"].iloc[0])


def test_single_digit_state_fips_is_zero_padded():
    # The CDL service rejects "9" for Connecticut ("The FIPS Code ... doesn't
    # exist") but accepts "09". Connecticut is the only Northeast state affected.
    from applebee.acquire import cdl

    assert cdl.STATE_FIPS["CT"] == 9
    assert f"{cdl.STATE_FIPS['CT']:02d}" == "09"
    assert f"{cdl.STATE_FIPS['PA']:02d}" == "42"


def test_prism_reader_accepts_both_delivery_formats(tmp_path):
    # PRISM switched from ESRI BIL to GeoTIFF: archived days are
    # PRISM_tmean_stable_4kmD2_20150501_bil.bil, freshly fetched ones are
    # prism_tmean_us_25m_20150501.tif. Verified bit-identical, so both must be
    # readable or archived and new days will not interoperate.
    from applebee.acquire import prism

    day = pd.Timestamp("2015-05-01")
    directory = prism._day_dir(tmp_path, "tmean", day)
    directory.mkdir(parents=True)

    assert not prism.already_have(tmp_path, "tmean", day)
    (directory / "prism_tmean_us_25m_20150501.tif").touch()
    assert prism.already_have(tmp_path, "tmean", day)

    other = prism._day_dir(tmp_path, "ppt", day)
    other.mkdir(parents=True)
    (other / "PRISM_ppt_stable_4kmD2_20150501_bil.bil").touch()
    assert prism.already_have(tmp_path, "ppt", day)


def test_national_cdl_url_is_well_formed():
    # The national CONUS raster avoids the state mosaic entirely: no border
    # padding, no per-state download failures, and it is served by USDA rather
    # than the GMU service that repeatedly went down mid-build.
    from applebee.acquire import cdl

    url = cdl.NATIONAL_URL.format(year=2018)
    assert url.endswith("2018_30m_cdls.zip")
    assert "nass.usda.gov" in url
