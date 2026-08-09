"""Tests for the Biddinger loader and panel construction (Objective 3b).

These pin the three things that would silently corrupt the evaluation: the
degree-suffixed coordinate text, the specimen-ID merge with Turley (which would
double-count 143 bees if it were a concatenation), and the ambiguous-zero rule.
"""

import numpy as np
import pandas as pd
import pytest

from applebee.evaluation import biddinger as B


# ---------------------------------------------------------------------------
# Coordinate parsing
# ---------------------------------------------------------------------------


def test_parses_degree_suffixed_coordinates():
    assert B._parse_degrees("39.958620°") == pytest.approx(39.95862)
    assert B._parse_degrees("-77.277220°") == pytest.approx(-77.27722)


def test_parses_plain_numbers_and_rejects_junk():
    assert B._parse_degrees(39.95862) == pytest.approx(39.95862)
    assert np.isnan(B._parse_degrees(None))
    assert np.isnan(B._parse_degrees("not a coordinate"))


def test_strips_hemisphere_letters():
    # Some rows carry the hemisphere as a letter rather than a sign.
    assert B._parse_degrees("39.95862°N") == pytest.approx(39.95862)


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------


def _specimens(rows):
    """Build a minimal specimen frame with the columns build_panel needs."""
    return pd.DataFrame(
        rows,
        columns=["col", "row", "year", "species", "trap_type"],
    )


def test_counts_are_per_cell_year():
    s = _specimens(
        [
            (1146, 240, 2015, "cornifrons", "V"),
            (1146, 240, 2015, "pumila", "V"),
            (1146, 240, 2016, "cornifrons", "V"),
        ]
    )
    panel = B.build_panel(s, cells=((1146, 240),), years=range(2015, 2017))
    assert panel.set_index("year")["observed"].to_dict() == {2015: 2, 2016: 1}


def test_species_filter_selects_one_species():
    s = _specimens(
        [
            (1146, 240, 2015, "cornifrons", "V"),
            (1146, 240, 2015, "pumila", "V"),
        ]
    )
    panel = B.build_panel(
        s, species="cornifrons", cells=((1146, 240),), years=range(2015, 2016)
    )
    assert panel["observed"].tolist() == [1]


def test_trap_type_filter_excludes_pan_traps():
    # Pan and blue vane do not overlap in time, so mixing them would confound
    # trap type with year.
    s = _specimens(
        [
            (1146, 240, 2015, "cornifrons", "V"),
            (1146, 240, 2015, "cornifrons", "P"),
        ]
    )
    panel = B.build_panel(s, cells=((1146, 240),), years=range(2015, 2016))
    assert panel["observed"].tolist() == [1]


def test_species_absence_in_a_sampled_year_is_a_real_zero():
    # pumila in 2016 proves the cell was sampled, so cornifrons == 0 is genuine
    # and must survive the ambiguous-zero filter.
    s = _specimens(
        [
            (1146, 240, 2015, "cornifrons", "V"),
            (1146, 240, 2016, "pumila", "V"),
        ]
    )
    panel = B.build_panel(
        s, species="cornifrons", cells=((1146, 240),), years=range(2015, 2017)
    )
    assert panel.set_index("year")["observed"].to_dict() == {2015: 1, 2016: 0}


def test_unsampled_year_is_dropped_by_default_and_kept_on_request():
    s = _specimens([(1146, 240, 2015, "cornifrons", "V")])
    years = range(2015, 2017)

    dropped = B.build_panel(s, cells=((1146, 240),), years=years)
    assert dropped["year"].tolist() == [2015]

    kept = B.build_panel(
        s, cells=((1146, 240),), years=years, drop_ambiguous_zeros=False
    )
    assert kept.set_index("year")["observed"].to_dict() == {2015: 1, 2016: 0}
    assert kept.set_index("year")["sampled"].to_dict() == {2015: True, 2016: False}


# ---------------------------------------------------------------------------
# The real file: the merge must be a union on specimen ID, never a concatenation
# ---------------------------------------------------------------------------


def test_specimen_ids_are_zero_padded_to_a_canonical_form():
    # Turley writes ten IDs with a four-digit suffix where this file always uses
    # five. Matching raw strings misses those and re-appends bees already present.
    assert B.normalise_id("DJB 2014-3176") == "DJB 2014-03176"
    assert B.normalise_id("DJB 2014-03176") == "DJB 2014-03176"
    assert B.normalise_id("  DJB 2014-3176  ") == "DJB 2014-03176"
    assert B.normalise_id("not an id") == "not an id"


def test_turley_merge_is_a_union_not_a_concatenation():
    merged = B.load_specimens(merge_turley=True)
    alone = B.load_specimens(merge_turley=False)

    # Once IDs are normalised, 151 of Turley's 183 Osmia records are already
    # present. Concatenating would double-count those 151.
    assert merged.n_shared == 151
    assert merged.n_turley_only == 32
    assert merged.dropped["kept"] == alone.dropped["kept"] + merged.n_turley_only


def test_the_merge_defaults_off_and_only_adds_omitted_species():
    # The extract is species-filtered. Every Turley record in the six species it
    # covers is already here, so a merge adds nothing but the three omitted
    # species -- and only for 2014-2019, biasing exactly the chapter's window.
    assert B.load_specimens().n_turley_only == 0, "merge_turley must default to False"

    merged = B.load_specimens(merge_turley=True).specimens
    added = merged[merged.source == "turley"]
    assert set(added.species) == {"atriventris", "texana", "conjuncta"}
    assert added.year.between(2014, 2019).all()


def test_extract_covers_exactly_the_six_documented_species():
    species = set(B.load_specimens().specimens.species)
    assert species == set(B.EXTRACT_SPECIES)


def test_the_merge_introduces_no_new_id_collisions():
    # The extract itself carries exactly one: DJB 2024-02023 appears as two
    # O. bucephala from different farms on different dates. Both rows are kept
    # deliberately. This pins the count so a *new* collision fails the suite.
    alone = B.load_specimens(merge_turley=False)
    merged = B.load_specimens(merge_turley=True)
    assert alone.duplicate_ids == ["DJB 2024-02023"]
    assert merged.duplicate_ids == alone.duplicate_ids


def test_every_kept_specimen_has_a_pennsylvania_location():
    kept = B.load_specimens().specimens
    assert kept["lat"].between(*B.PA_LAT_RANGE).all()
    assert kept["lon"].between(*B.PA_LON_RANGE).all()
    assert kept["year"].notna().all()
