"""Acquire AppleBee's inputs from source, rather than depending on a fixed extent.

Two pipelines, both validated against the archived Pennsylvania inputs:

``grid``
    The PRISM 4 km grid generated arithmetically. Reproduces the ``(col, row)``
    keys of every archived Pennsylvania cell exactly.

``prism``
    Daily PRISM weather from the public NACSE endpoint, sampled onto grid cells
    and written straight to the cache :mod:`applebee.weather` reads.

``cdl``
    The Lonsdorf spring forage index, built from the USDA Cropland Data Layer
    with Koh et al. (2016) expert values. Reproduces ``archives/data/forage.csv``
    at r = 0.985-0.992.

Needs the optional geospatial extras: ``rasterio``, ``exactextract``,
``geopandas``, ``requests``.
"""

from . import cdl, grid, prism  # noqa: F401

__all__ = ["cdl", "grid", "prism"]
