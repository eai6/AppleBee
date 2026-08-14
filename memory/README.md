# memory/

Session log for work on this repo. One file per session or per distinct piece of
work, numbered in the order it happened.

## Naming convention

```
<n>_<purpose_or_definition_of_task>_plan.md
```

- `<n>` — increments monotonically: `1_`, `2_`, `3_`, …
- `<purpose_or_definition_of_task>` — short snake_case description of the task
- always ends in `_plan.md`

Examples:

```
1_memory_folder_setup_plan.md
2_calibrate_emergence_thresholds_plan.md
3_fix_centrella_brood_cell_extract_plan.md
```

## What goes in a file

Each file is a working record, written at the start of a session and updated as
the work goes:

1. **Date** and one-line purpose
2. **Context** — what state the repo was in, why this work is being done
3. **Plan** — the steps, as a checklist
4. **Progress / outcome** — what actually happened, including what did not work
5. **Commits** — every commit made under this plan (see below)
6. **Follow-ups** — anything left open, which usually becomes the next numbered file

## Linking commits to plans

Every commit made while working on a plan carries a `Plan:` trailer naming the
plan file:

```
Fix emergence degree-day accumulation start date

The archived implementation started accumulating on 1 Jan rather than
1 Mar, shifting emergence ~6 days early in warm years.

Plan: 2_calibrate_emergence_thresholds_plan.md
Co-Authored-By: ...
```

The link is recorded in both directions:

- **commit → plan** — the `Plan:` trailer in the commit message
- **plan → commit** — a `## Commits` table in the plan file, with SHA, date, and
  subject, filled in as commits land

Finding the work that came from a plan:

```bash
git log --grep="Plan: 2_"                 # all commits under plan 2
git log --format='%h %s%n  %(trailers:key=Plan,valueonly)'   # plan for each commit
```

Rules:

- One plan per commit. If a change genuinely spans two plans, split the commit.
- A commit with no plan (typos, formatting, a one-line fix) may omit the trailer —
  but if it needed thinking, it needed a plan.
- The plan file's own creation commit is part of that plan, so it carries the
  trailer too.

## Index

| # | File | Purpose |
|---|---|---|
| 1 | [1_memory_folder_setup_plan.md](1_memory_folder_setup_plan.md) | Establish this session-tracking folder |
| 2 | [2_replication_diagnosis_and_data_organisation_plan.md](2_replication_diagnosis_and_data_organisation_plan.md) | Pin down what does not replicate and why; consolidate simulation inputs under `data/` |
| 3 | [3_biddinger_objective3_evaluation_plan.md](3_biddinger_objective3_evaluation_plan.md) | *(withdrawn)* Rebuild Objective 3 on the Biddinger database — data and code removed 2026-08-13 |
| 4 | [4_data_acquisition_pipeline_plan.md](4_data_acquisition_pipeline_plan.md) | Build PRISM and CDL→forage acquisition pipelines so the simulation extent is not fixed to Pennsylvania |
| 5 | [5_northeast_simulation_and_web_report_plan.md](5_northeast_simulation_and_web_report_plan.md) | Run AppleBee across the Northeast on the acquired inputs; publish a web report |
| 6 | [6_paper_analysis_notebook_and_input_provenance_plan.md](6_paper_analysis_notebook_and_input_provenance_plan.md) | Recast the notebook as the paper's reproducible analysis; secure and document every input |
