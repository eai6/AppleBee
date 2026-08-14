"""AppleBee: an individual-based spatially explicit mechanistic model of
reproductive success in the solitary bee *Osmia cornifrons*.

Reimplementation of Chapter 4 of Amoah et al., *Bridging AI and Ecology*.
"""

from .config import ModelParams, SOBOL_PROBLEM
from .forage import ForageGrid
from .model import AppleBee, GridYearResult
from .weather import WeatherGrid, load_matrices, load_weather
from . import datasets  # imported last: it depends on the names above

__all__ = [
    "AppleBee",
    "ForageGrid",
    "GridYearResult",
    "ModelParams",
    "SOBOL_PROBLEM",
    "WeatherGrid",
    "datasets",
    "load_matrices",
    "load_weather",
]
