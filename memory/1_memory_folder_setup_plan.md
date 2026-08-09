# 1 — Memory folder setup

**Date:** 2026-08-05
**Purpose:** Establish a `memory/` folder in the repo to track sessions, plans,
and outcomes across work on the AppleBee model.

## Context

Repo state at the start of this session:

- Branch `main`, at `6cf4705 Reimplement AppleBee model in Python with full replication`
- Preceding commits: `bb40d38 refactoring`, `9cd6c10 data extraction code`
- Untracked: `data/` (holds `cache/` and `raw/`, built by `scripts/build_cache.py`)

The project is a clean-room Python reimplementation of Chapter 4 of *Bridging AI
and Ecology* — an individual-based model of *Osmia cornifrons* reproductive
success driven by PRISM daily weather and a Lonsdorf spring floral index. The
original exploratory R/Python code lives unchanged in `archives/`.

Work on this project spans several long-running threads (replication, calibration,
sensitivity analysis, figures), so a durable per-session record is worth keeping
in the repo rather than only in chat history.

## Plan

- [x] Create `memory/` at the repo root
- [x] Write `memory/README.md` documenting the naming convention and file structure
- [x] Write this file as entry `1`
- [x] Add an index table to `memory/README.md`
- [x] Define how commits link back to plans

## Outcome

`memory/` created with:

- `README.md` — convention (`<n>_<purpose_or_definition_of_task>_plan.md`),
  expected file sections, the commit-linking rule, and the running index
- `1_memory_folder_setup_plan.md` — this file

Conventions agreed:

- The number increments for each new task or plan; it reflects order of work,
  not priority.
- Every commit made under a plan carries a `Plan: <n>_<slug>_plan.md` trailer, so
  `git log --grep="Plan: 3_"` recovers all work done under plan 3. Each plan file
  mirrors the link in a `## Commits` table.

## Commits

| SHA | Date | Subject |
|---|---|---|
| _pending_ | 2026-08-05 | Add memory/ session log with plan-to-commit convention |

## Open threads in the project

Carried forward from `README.md` and `docs/REPLICATION_NOTES.md`, as candidates
for future numbered entries:

- **Objective 2 R² gap** — the archived Centrella et al. (2020) extract records
  emerged adults rather than the brood-cell counts the chapter describes, so the
  absolute R² does not reproduce (see §3 of the replication notes).
- `data/` is untracked and rebuilt from `archives/output/` via
  `scripts/build_cache.py`; note this whenever a session depends on the cache.

## Follow-ups

- Next session: add entry `2_...` before starting work, not after.
