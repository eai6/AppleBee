"""Tests for what the hosted platform answers.

Two things are pinned here beyond the arithmetic. First, that the API reproduces
the paper: a request with default parameters must return the numbers the
manuscript reports, or the platform and the paper have drifted. Second, that
every answer carries its caveats — a payload that returned R² 0.803 without
saying the slope is not significant would overstate what the model earned, and
that is a contract, not a nicety.
"""

import pytest

from applebee import api, datasets
from applebee.config import ModelParams
from web.app import answer, handler

NORTHEAST = datasets.DATASETS["northeast"].available
PENNSYLVANIA = datasets.DATASETS["pennsylvania"].available
needs_northeast = pytest.mark.skipif(not NORTHEAST, reason="northeast inputs absent")
needs_evaluation = pytest.mark.skipif(not PENNSYLVANIA, reason="pennsylvania inputs absent")

# The New York orchard whose cell the manuscript's Objective 2 uses.
ORCHARD = (42.87, -77.01)


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------


def test_every_parameter_is_described_for_the_form():
    spec = api.parameters()
    described = {f["name"] for f in spec["parameters"]}
    assert described == set(ModelParams().to_dict())


def test_the_form_defaults_are_the_model_defaults():
    # The form must not carry its own copy of the numbers.
    for field in api.parameters()["parameters"]:
        assert field["default"] == ModelParams().to_dict()[field["name"]]


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


@needs_evaluation
def test_defaults_reproduce_the_published_evaluations():
    result = api.evaluate()
    assert result["objective_2"]["r2"] == 0.510
    assert result["objective_2"]["n"] == 51 and result["objective_2"]["sites"] == 17
    assert result["objective_3"]["r2"] == 0.803
    assert result["objective_3"]["rmse"] == 7.52
    assert result["objective_3"]["n"] == 6


@needs_evaluation
def test_objective_3_is_reported_as_not_significant():
    objective_3 = api.evaluate()["objective_3"]
    assert objective_3["p"] == pytest.approx(0.358, abs=0.001)
    assert objective_3["significant"] is False
    assert "least squares" in objective_3["p_basis"]


@needs_evaluation
def test_an_answer_always_carries_the_six_point_caveat():
    for payload in (api.evaluate(), api.point(*ORCHARD)):
        assert any("not significant" in c for c in payload["caveats"])


@needs_evaluation
def test_changed_parameters_are_reported_alongside_a_baseline():
    result = api.evaluate({"temperature_threshold": 16.0})
    assert result["differences"]["temperature_threshold"] == {"default": 13.9, "used": 16.0}
    assert result["baseline"]["objective_2"]["r2"] == 0.510
    assert result["objective_2"]["r2"] != 0.510


@needs_evaluation
def test_defaults_are_not_compared_against_themselves():
    assert "baseline" not in api.evaluate()


def test_an_unknown_parameter_is_refused():
    with pytest.raises(ValueError, match="temperature_thresold"):
        api.evaluate({"temperature_thresold": 16.0})


# ---------------------------------------------------------------------------
# point
# ---------------------------------------------------------------------------


@needs_northeast
def test_a_point_resolves_to_the_cell_it_falls_in():
    result = api.point(*ORCHARD)
    assert result["location"]["distance_km"] < 5      # the grid is 4 km
    assert result["location"]["outside_region"] is False
    assert len(result["springs"]) == 6
    assert [s["spring"] for s in result["springs"]] == [2014, 2015, 2016, 2017, 2018, 2019]


@needs_northeast
def test_a_point_reports_the_drivers_not_just_the_answer():
    spring = api.point(*ORCHARD)["springs"][0]
    assert {"offspring_per_female", "eggs_per_female", "emergence_date",
            "days_lost_to_cold", "days_lost_to_rain",
            "forage_index"} <= set(spring)


@needs_northeast
def test_parameters_change_the_prediction():
    at = lambda params: [s["offspring_per_female"]
                         for s in api.point(*ORCHARD, params)["springs"]]
    default, strict = at(None), at({"temperature_threshold": 25.0})
    # A stricter foraging threshold can only remove foraging days, never add
    # them, so every spring falls or holds and the season as a whole falls.
    assert all(s <= d for s, d in zip(strict, default))
    assert sum(strict) < sum(default)
    # And a threshold no spring day in upstate New York reaches leaves nothing.
    assert at({"temperature_threshold": 35.0}) == [0.0] * 6


@needs_northeast
def test_a_point_outside_the_region_is_refused_rather_than_relocated():
    with pytest.raises(ValueError, match="does not cover it"):
        api.point(19.4, -99.1)      # Mexico City


@needs_northeast
def test_a_point_near_the_edge_says_which_cell_answered():
    # Far enough to be a different place, close enough to still be worth serving.
    result = api.point(45.5, -83.5)
    if result["location"]["distance_km"] > api.FAR_KM:
        assert result["location"]["outside_region"] is True
        assert any("km away" in c for c in result["caveats"])


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


@needs_northeast
def test_a_point_can_be_asked_for_with_a_query_string():
    status, payload = answer("GET", "/api/point", {"lat": "42.87", "lon": "-77.01"}, None)
    assert status == 200 and payload["springs"]


def test_a_missing_coordinate_is_a_400_not_a_stack_trace():
    status, payload = answer("GET", "/api/point", {"lon": "-77.01"}, None)
    assert status == 400 and "lat is required" in payload["error"]


def test_an_unparseable_coordinate_says_so():
    status, payload = answer("GET", "/api/point", {"lat": "north", "lon": "-77"}, None)
    assert status == 400 and "must be a number" in payload["error"]


def test_an_unknown_parameter_comes_back_as_400_naming_it():
    status, payload = answer("POST", "/api/evaluate", {}, {"parameters": {"nope": 1}})
    assert status == 400 and "nope" in payload["error"]


def test_an_unknown_route_is_404():
    status, payload = answer("GET", "/api/elsewhere", {}, None)
    assert status == 404 and "no route" in payload["error"]


def test_the_lambda_envelope_is_json_and_cacheable():
    response = handler({"rawPath": "/api/parameters",
                        "requestContext": {"http": {"method": "GET"}}})
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert "max-age" in response["headers"]["cache-control"]


def test_a_failed_lambda_response_is_not_cached():
    response = handler({"rawPath": "/api/elsewhere",
                        "requestContext": {"http": {"method": "GET"}}})
    assert response["statusCode"] == 404
    assert response["headers"]["cache-control"] == "no-store"


def test_a_malformed_body_is_reported_rather_than_raised():
    response = handler({"rawPath": "/api/evaluate", "body": "{not json",
                        "requestContext": {"http": {"method": "POST"}}})
    assert response["statusCode"] == 400 and "not JSON" in response["body"]


# ---------------------------------------------------------------------------
# region
# ---------------------------------------------------------------------------


@needs_northeast
def test_a_block_answers_for_its_own_slice_only():
    payload = api.region(block=(0, 50))
    assert payload["cells"] == 50
    assert payload["summary"]["cell_years"] == 50 * len(payload["springs"])


@needs_northeast
def test_the_packed_payload_unpacks_to_what_the_model_produced():
    import base64

    import numpy as np

    payload = api.region(block=(0, 50))
    scale = payload["encoding"]["scale"]
    unpack = lambda blob, kind: np.frombuffer(base64.b64decode(blob), dtype=kind)
    mean = unpack(payload["mean"], "uint16") / scale
    springs = np.stack([unpack(payload["by_spring"][str(s)], "uint16") / scale
                        for s in payload["springs"]])
    assert mean.size == 50
    assert unpack(payload["lon"], "float32").size == 50
    # The mean array must be the mean of the years, not a separately rounded one.
    assert np.allclose(mean, springs.mean(axis=0), atol=1 / scale)


@needs_northeast
def test_the_payload_carries_the_grid_step_so_a_map_can_draw_cells():
    # PRISM's 4 km grid is 1/24 of a degree; a client that guessed would stripe.
    assert api.region(block=(0, 200))["cell_degrees"] == pytest.approx(1 / 24, abs=1e-4)


@needs_northeast
def test_region_parameters_travel_with_the_answer():
    payload = api.region({"longevity": 30}, block=(0, 20))
    assert payload["differences"]["longevity"] == {"default": 22, "used": 30}
    assert payload["parameters"]["longevity"] == 30


def test_a_cached_region_says_that_it_was_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REGION_CACHE", tmp_path)
    api._cache_write("k", {"region": "northeast", "cells": 3})
    assert api._cache_read("k")["cached"] is True
    assert api._cache_read("absent") is None


def test_the_cache_key_follows_the_parameters():
    from applebee.config import ModelParams

    default = api._region_key("northeast", [2013], ModelParams(), None)
    changed = api._region_key("northeast", [2013],
                              ModelParams().with_(longevity=30), None)
    other_years = api._region_key("northeast", [2014], ModelParams(), None)
    assert len({default, changed, other_years}) == 3


def test_a_region_run_is_started_rather_than_waited_for(tmp_path, monkeypatch):
    # 268,536 cell-years takes longer than any HTTP request should, so a miss
    # starts the work and says so instead of holding the connection open until
    # the platform's own gateway gives up on it.
    monkeypatch.setattr(api, "REGION_CACHE", tmp_path)
    started = []
    monkeypatch.setattr("web.app.threading.Thread",
                        lambda **kw: type("T", (), {"start": lambda s: started.append(kw)})())
    status, payload = answer("POST", "/api/region", {}, {"parameters": {"longevity": 29}})
    assert status == 202
    assert payload["status"] == "running" and payload["retry_after_seconds"] > 0
    assert len(started) == 1


def test_a_finished_region_run_is_returned_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REGION_CACHE", tmp_path)
    key = api.region_key({"longevity": 28})
    api._cache_write(key, {"region": "northeast", "cells": 3})
    status, payload = answer("POST", "/api/region", {}, {"parameters": {"longevity": 28}})
    assert status == 200 and payload["cached"] is True


# ---------------------------------------------------------------------------
# area, places, download
# ---------------------------------------------------------------------------


@needs_northeast
def test_a_radius_averages_the_cells_inside_it():
    answer = api.area(lat=42.87, lon=-77.01, radius_km=8)
    assert answer["location"]["cells"] > 1
    assert len(answer["springs"]) == 6
    # Every driver is a real per-cell-year quantity, not a placeholder: the
    # emergence date has to move between seasons.
    dates = {s["emergence_date"] for s in answer["springs"]}
    assert len(dates) > 1


@needs_northeast
def test_a_drawn_shape_takes_the_cells_whose_centres_fall_inside():
    ring = [[-77.1, 42.8], [-76.9, 42.8], [-76.9, 42.95], [-77.1, 42.95]]
    answer = api.area(polygon=ring)
    assert answer["location"]["kind"] == "polygon"
    assert answer["location"]["cells"] >= 4


def test_a_shape_smaller_than_a_cell_is_refused_with_advice():
    with pytest.raises(ValueError, match="wider"):
        api.area(polygon=[[-77.0, 42.8], [-76.999, 42.8], [-76.999, 42.801]])


def test_a_shape_needs_three_corners():
    with pytest.raises(ValueError, match="three corners"):
        api.area(polygon=[[-77.0, 42.8], [-76.9, 42.9]])


def test_an_area_needs_either_a_shape_or_a_radius():
    with pytest.raises(ValueError, match="polygon"):
        api.area(lat=42.87, lon=-77.01)


@needs_northeast
def test_the_download_is_one_row_per_cell_and_one_column_per_spring():
    csv = api.download(years=[2018, 2019])
    header, first, *rest = csv.splitlines()
    assert header == "lon,lat,spring_2018,spring_2019"
    # Every cell in the region, once -- not a hardcoded count, which would just
    # have to be edited whenever the region's definition changes.
    assert len(rest) + 1 == len(api._runnable_cells("northeast"))
    assert len(first.split(",")) == 4


@needs_northeast
def test_asking_for_a_spring_that_was_never_run_says_which_exist():
    with pytest.raises(ValueError, match="this run covers"):
        api.download(years=[1999])


def test_a_search_for_nothing_returns_nothing_rather_than_failing():
    assert api.places("")["places"] == []


@needs_northeast
def test_an_area_reports_its_spread_not_only_its_average():
    # A mean over hundreds of cells hides a three-fold range and a skew, so the
    # median and the extremes travel with it.
    answer = api.area(polygon=[[-77.1, 42.7], [-76.3, 42.75],
                               [-76.1, 42.2], [-76.9, 41.95]])
    spring = answer["springs"][-1]
    spread = spring["spread"]["offspring"]
    assert spread["min"] < spring["offspring_per_female"] < spread["max"]
    assert spread["sd"] > 0
    earliest = spring["spread"]["emergence"]["earliest"]
    latest = spring["spread"]["emergence"]["latest"]
    assert earliest < spring["emergence_date"] < latest


@needs_northeast
def test_one_cell_has_no_spread_to_report():
    assert "spread" not in api.point(42.87, -77.01)["springs"][0]


@needs_northeast
def test_the_region_is_a_set_of_states_not_a_bounding_box():
    # The grid was built from a rectangle that cuts Ohio, Kentucky and Virginia
    # off mid-state. Membership is what decides which cells are in the region.
    cells = api._runnable_cells("northeast")
    assert len(cells) < 44_756                     # the rectangle held this many
    # A bounding box would reach to -83.0 and 36.5 exactly, with straight edges.
    assert cells["lon"].min() > -83.0
    assert cells["lat"].min() > 36.5
