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
