# 6 — Paper analysis notebook and input provenance

**Date:** 2026-08-13
**Purpose:** Turn the replication notebook into the analysis document for a paper
based on the dissertation — one a reader can reproduce from documented inputs and
configurable parameters, rather than an audit against the chapter.

## The shift

Plans 2–5 asked *does this reproduce the dissertation?* The notebook was built
around that question: every value asserted against `docs/REPLICATION_NOTES.md`,
chapter figures printed beside each result, a self-check cell that failed if
anything drifted.

That framing has served its purpose. The author's intent now is a paper, where
the results stand on their own and the reader's question is *can I run this
myself?* So the chapter comparisons, the `check()` machinery and the
replicates/fails verdicts come out, and what a reader needs to reproduce the work
goes in ahead of any result.

`notebooks/applebee_replication.ipynb` → `notebooks/applebee_analysis.ipynb`.

## Structure

Two documentation sections precede the analyses:

- **§ A Inputs** — every dataset's source URL, retrieval date, coverage,
  validation, the command that rebuilds it, and a SHA-256 checked live
- **§ B Parameters** — all 18 `ModelParams` fields with meanings, the three ways
  to supply them, and a TOML example that round-trips in the notebook

Then three analyses: egg production (Centrella), the whole model (Turley), and
the Northeast simulation.

## Two gaps this exposed

**The Koh lookup was unsecured.** `applebee/acquire/cdl.py` read
`cdl_reclass_koh.csv` from `archives/data/CDL/`, which `.gitignore` excludes — so
the table defining every forage value in the model was untracked and would be
absent from a fresh clone. Copied to
`data/inputs/forage/koh_2016_cdl_floral_index.csv` (12 KB, 134 CDL classes) and
`config.KOH_FLORAL_CSV` added; the archive copy remains as a fallback.

**Only `weather/` carried provenance.** `forage/` and `observations/` had none.
Both now have a `PROVENANCE.json` with sources, DOIs, method, validation, known
gaps and per-file hashes. All 25 input files across the three folders are
documented.

`applebee/provenance.py` makes the records actionable: `summary()`, `verify()`
(size, instant), `verify(full=True)` (SHA-256, minutes at 8.4 GB), `report()`.

## Extent

Narrowed from the contiguous United States to the **Northeast** (44,756 cells ×
6 years). Both evaluations are northeastern, so that is where the model has been
tested, and the CONUS maps carry a known low-latitude artefact — see below. The
CONUS outputs remain on disk.

A 16-year Pennsylvania section was built and then removed at the author's
direction (2026-08-14); `scripts/simulate.py --region pennsylvania` still
produces it, and it reproduces the dissertation-era run exactly on all 119,232
cell-years.

## Statistical findings recorded under plan 2

Investigating whether the mixed models matched the dissertation surfaced two
things, written up in `docs/REPLICATION_NOTES.md` §2 rather than here:

- the conditional R² for Objective 3 is arithmetically forced —
  `1 − (1 − marginal)/4`, shrinkage exactly ½ at every year, because one
  observation per group makes the variance components non-identifiable
- β and its p-value do **not** replicate (1.99 at p = 0.001 against the chapter's
  1.82, p > 0.05); `statsmodels` gives a standard error 3.1× smaller than OLS

The author's decision (2026-08-14) is to report the **conditional R²**, as the
dissertation does, pending a statistician's advice. The notebook reports it and
keeps the design diagnostics beneath it, labelled as diagnostics.

## An artefact worth carrying into the paper

The foraging criterion is applied to **daily mean** temperature. Where the
diurnal range is wide, a day averaging below the 13.9 °C threshold may still have
had a usable afternoon, so unsuitable days are over-counted — worst at low
latitudes. This is why the southern United States looks poor in the CONUS maps,
and part of why the extent is now the Northeast.

Investigating spring 2014 in the South also produced a clean method: hold each
cell fixed and swap one factor at a time. Swapping the weather removed the whole
penalty (13.47 → 10.53 cold days); swapping the emergence date within 2013 removed
none (13.47 → 13.88). It was the weather, not early emergence.

## Commits

| SHA | Date | Subject |
|---|---|---|
| `33a8004` | 2026-08-14 | Recast the notebook as the paper's analysis, and secure every input |

## Follow-ups

- `tmax` is available from the same PRISM endpoint; re-running the criterion
  against it would quantify the daily-mean artefact
- Pennsylvania weather traces to the dissertation archive rather than a
  re-fetchable source, so PA alone cannot be rebuilt from a clone
