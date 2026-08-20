# 7 — Web platform for running and extending the simulation

**Date:** 2026-08-19
**Purpose:** Put AppleBee on the web so a reviewer can re-run the analysis under
their own parameters, and so the input data can be extended without a laptop —
building toward an October forecast of next spring's abundance for growers.
Deployed on AWS, cheap enough to leave running.

## Context

The model, its inputs and its analysis are already reproducible from a clone
(plan 6): `notebooks/applebee_analysis.ipynb` runs end to end, every input
carries a `PROVENANCE.json` with a SHA-256, and every parameter is a field of
`ModelParams` with per-run overrides from JSON/TOML. What does not exist is any
way to use it without Python, a clone and 10 GB of inputs.

Plan 5 published a static web report of one run. This plan is the next step: not
a report of a run someone else did, but a place to *do* runs.

## What the notebook says the platform must be

The notebook is the specification. Its five sections map onto the product, and
the audit turns up one fact that decides the architecture — **the reviewer-facing
computations are tiny, and only the map is big**.

| Notebook | Platform surface | Cost to serve |
|---|---|---|
| § A Inputs — source, coverage, SHA-256, `verify()` | Provenance panel; integrity badge per input | static JSON |
| § B Parameters — 18 fields, `from_file`, `differences()` | The parameter form; a misspelled key **raises** rather than silently defaulting | none |
| § 1 Egg production — 51 obs, 17 NY sites | Re-fit under the user's parameters; returns R², β, p, ICC | 34 KB of weather, ~0.2 s |
| § 2 Whole model — 6 annual counts, 1 PA cell | Re-fit under the user's parameters | one cell, ~0.1 s |
| § 3 Simulation — 44,756 cells × 6 years | The regional map | 1.8 GB of weather, ~35 s |

So "let a reviewer change a parameter and see what happens to the paper's
results" — the single most valuable feature — costs almost nothing to run. The
expensive path is only the regional map, and even that is seconds, not hours.

## Measured facts this plan rests on

Timed on this machine, 2026-08-19:

- **268,536 cell-years in 34–38 s** single-core; 200 cells × 6 years in 0.15 s;
  one cell-year in **0.1 ms**. Model load (memmap) 0.6 s.
- The weather matrices are `(n_cells, n_days)` float32 in C order, so **one
  cell's series is 8,764 contiguous bytes**. A single location needs ~18 KB of
  weather, fetchable as two S3 ranged GETs against the files we already have —
  no re-formatting, no database.
- Inputs on disk: weather 10 GB (Northeast 1.7, CONUS 7.9), forage 736 MB.
  Northeast simulation output is **4.4 MB** of parquet.
- Plan 5's web report packed 268,536 values into a **933 KB** payload as base64
  `Uint16`. That technique is reused rather than reinvented.

External constraints, checked 2026-08-19:

- **PRISM 4 km is free and redistributable** with attribution requested. But the
  download service allows **two fetches per file per 24 h and blocks IPs for
  excessive activity**, and PRISM is *not* published on AWS Open Data in any
  cloud-native form. So we keep our own copy in S3, and acquisition is a single
  throttled background worker — never a synchronous user action.
- **CDL for crop year Y is released Feb of Y+1** (2025's layer came 2026-02-27).
  An October forecast for spring Y+1 therefore cannot have year-Y forage and must
  use the most recent CDL. Plan 4 measured year-to-year forage stability at
  **r = 0.992–0.995, mean absolute change 0.007–0.009**, which is what makes the
  substitution defensible — and it must be stated on the forecast, not hidden.
- The model reads weather from 1 January to **1 October** and attributes offspring
  to the following spring. The October forecast is not a new capability bolted
  on; it is exactly what the model already computes, surfaced on the day its
  inputs complete.

## Access: what each option actually costs

Asked before choosing. Two findings invert the usual assumption.

| Option | Monthly cost | What drives it |
|---|---|---|
| Public + in-Lambda rate limit | **$0** | A DynamoDB counter per IP, on-demand. Abusive requests are rejected in ~1 ms of Lambda time. |
| Public + AWS WAF rate rule | **+$6-7** | $5 per web ACL + $1 per rule + $0.60/M requests. More than the entire rest of the platform. |
| Unlisted link + shared password | **$0** | One secret checked in the Lambda. |
| Real accounts (Cognito) | **$0** | 10,000 monthly active users are free indefinitely on the Lite/Essentials tiers. |

So **auth is not what costs money — edge filtering is.** Cognito is free at any
plausible scale for this platform; its price is build time and login friction,
not dollars. WAF is the one line item that would multiply the bill, and it buys
protection this platform can get for nothing by rate-limiting inside the Lambda
and capping reserved concurrency so the ceiling is structural.

Recommendation: **public, rate-limited in-Lambda, no WAF, no login at launch.**
Add Cognito only when growers want a saved location and an emailed forecast —
at which point it is still free.

## Architecture

Static front end, serverless back end, no always-on compute.

```
CloudFront ──► S3 (SPA: html/js, provenance JSON, cached run payloads)
     │
     ├──► Lambda URL  /evaluate   re-fit Objectives 2 & 3      ~0.5 s
     ├──► Lambda URL  /point      one location, one run         ~0.2 s
     └──► Lambda URL  /region     fan-out map run               ~5 s
                          │
                          └─► N parallel Lambdas, 5,000 cells each,
                              S3 ranged reads on the .npy matrices
S3 (inputs, unchanged layout) ◄── Fargate worker on EventBridge schedule
                                  runs scripts/fetch_prism.py + build_forage.py
                                  behind a DynamoDB lock (one fetcher, ever)
```

Decisions and why:

- **Lambda Function URLs, not API Gateway.** Function URLs are free; API Gateway
  is $1–3.50 per million requests for no benefit at this scale.
- **Ranged reads instead of a big container or EFS.** Because rows are
  contiguous, a worker handling cells *i…i+5000* issues one ranged GET of 44 MB
  per variable. No 2 GB container image, no EFS bill, and the fan-out puts a
  regional run at ~5 s wall clock instead of 35 s.
- **Results cache keyed by hash of (region, years, parameters).** Identical
  requests — the common case, since most visitors will run the defaults — are
  served from S3 for free. Only genuinely new parameter sets cost compute.
- **The acquisition pipeline is not exposed as a user action.** Users *request*
  an extension; a queued worker runs it. This is a hard requirement, not caution:
  concurrent PRISM fetching gets the IP blocked and takes the platform's data
  supply with it.
- **Region definitions move from code to data.** `applebee/datasets.py` currently
  hard-codes three `Dataset(...)` entries; extending coverage from the web needs
  them to be rows in a config the worker writes.

## Cost

Steady state, us-east-1, Northeast only, public and rate-limited in-Lambda.
Weather grows from 1.7 GB to ~4.2 GB once the backfill brings 2013-2018 up to
2013-2026; forage and observations add ~0.3 GB.

| Item | Basis | Monthly |
|---|---|---|
| S3 storage | 4.5 GB x $0.023 | $0.10 |
| S3 requests | 2 ranged GETs per point run; 20 per regional run | ~$0.01 |
| Lambda, all three endpoints | ~15,000 GB-s/month against a 400,000 GB-s always-free tier | $0 |
| Lambda, daily ingest | 365 invocations, seconds each | $0 |
| CloudFront | free tier is 1 TB out + 10M requests, always free | $0 |
| DynamoDB rate-limit counters | on-demand, ~100k writes | ~$0.13 |
| CloudWatch Logs | with 14-day retention | ~$0.10 |
| **Total** | | **under $0.50** |

A custom domain adds $0.50/month for the Route 53 hosted zone plus registration
(~$12-15/year), taking it to **roughly $1.50/month all in**.

One-time: the Fargate worker for the backfill is 1 vCPU for ~8.5 h, about
**$0.42**. Data transfer in is free.

Lambda only leaves the free tier past roughly 3,800 regional runs a month, which
is far beyond any plausible reviewer traffic, and the results cache absorbs the
repeat requests that would otherwise get closest to it.

### What would actually make this expensive

Three AWS traps, none of which this design needs:

- **A NAT Gateway** — $0.045/h, **$32/month**, 60x the whole platform. Incurred
  by putting Lambdas in a VPC for no reason. The design keeps them out of a VPC.
- **AWS WAF** — $6-7/month for rate limiting that a DynamoDB counter does free.
- **Unbounded CloudWatch Logs** — $0.50/GB ingested. Set retention at creation.

## The blocker for the grower feature: the data stops in 2018

A forecast made in October 2026 for spring 2027 needs weather from 1 January to
1 October 2026. The repository holds 2013-2018. Nothing about the model or the
platform is in the way — the inputs simply have to be brought forward, and the
existing pipeline already does it.

Measured with `prism.estimate()` on 2026-08-19:

| Job | Files | Download | Wall clock |
|---|---|---|---|
| PRISM backfill 2019-2025 | 5,114 variable-days | 10.5 GB | ~6.4 h |
| PRISM current year to 1 Oct | 548 variable-days | 1.1 GB | ~0.7 h |
| CDL 2019-2025, national | 7 rasters | ~21 GB transient | ~1.4 h |
| **Total, one time** | | **~33 GB transient** | **~8.5 h unattended** |

Thereafter the increment is **two files a day, ~4 MB, seconds** — an EventBridge
rule and a small Lambda, not a Fargate task.

Two consequences worth stating plainly:

- The grower feature is one overnight job away, not a research project.
- The forecast's forage index will always be the previous year's CDL, because
  NASS publishes crop year Y in February of Y+1. Plan 4 measured year-to-year
  forage stability at r = 0.992-0.995, which is what makes that acceptable — and
  the forecast must say so on its face.

## Phases

Decided: Northeast only; extension is admin-run on user request; and the build
aims at growers while carrying the reviewer surface in the same release. Those
two audiences share a spine — both are small computations over tiny slices of
data — so they ship together rather than in sequence.

- [x] **Phase 0 - plumbing.** Done 2026-08-19; see Progress below.
- [ ] **Phase 1 - bring the data to the present.** *Deferred 2026-08-19: this
      runs later, through the admin path, once the platform exists.* The
      platform is therefore built against 2013-2018 and is fully exercisable on
      it — only the forecast needs data that does not exist yet.
- [x] **Phase 2 - the two endpoints that matter.** Done 2026-08-19. `/point` (a location, a year,
      offspring per female and the drivers behind it) and `/evaluate` (Objectives
      2 and 3 re-fitted under the visitor's parameters). One page, two audiences:
      a grower enters an address, a reviewer opens the parameter form. Both are
      sub-second Lambdas over kilobytes of data.
- [x] **Phase 3 - the map.** Done 2026-08-19. `/region` fan-out, packed payload, canvas map reusing
      plan 5's encoding, results cache keyed by parameter hash.
- [~] **Phase 4 - extension on request.** Queue and gating done 2026-08-19;
      the Fargate worker that runs it needs the AWS account. Queued admin-approved jobs for new years
      or a new extent, provenance and SHA-256 written on every S3 object so the
      integrity story survives the move off disk. **Its first real job is the
      backfill deferred from Phase 1**, which makes this path load-bearing rather
      than incidental: it must survive an 8.5 h run, so the worker is Fargate
      (Lambda's 15-minute ceiling rules it out), job state is durable enough to
      report and resume, and `fetch_prism.py`'s existing resumability is what it
      leans on. Dogfooding the hardest job it will ever run is a decent test.
- [ ] **Phase 5 - the October moment.** Scheduled run on 1 October, a forecast
      page that states its uncertainty, and optionally accounts so a grower is
      told rather than having to check.

## Decisions taken

- **Northeast only**, given the evaluation limitation. CONUS stays out of the
  platform until the model is tested outside the region it was evaluated in.
- **Extension is admin-run**; users request it. Protects the PRISM fetch.
- **Growers are the goal**, reviewers are served by the same spine.
- **The backfill waits** and runs through the admin path once that exists, so
  the platform is built and shipped against the data already on disk.
- **Public and rate-limited in-Lambda**, no WAF, no login at launch.

## Open questions

1. Domain name, and whether it lives under a Penn State host or independently.
2. Whether the October forecast is opt-in by email (needs accounts, still free)
   or purely a page a grower visits.

## Progress

### Phase 0 — done 2026-08-19

**`applebee/remote.py`** — a `RemoteMatrix` that stands in for the memory-mapped
array inside a `WeatherGrid`, reading rows as byte ranges. Reads go through a
`Ranges` reader: `HttpRanges` for S3 or CloudFront, `FileRanges` for a local
path, so the whole remote path is testable without a network and a deployment
can point at local files without changing anything else.

Verified against the real Northeast matrices: shapes, dates and cell tables
match, sampled series are byte-identical, and a six-year model run over the same
cells returns a frame that `.equals()` the local one. A contiguous row block is
one request (44 MB for 5,000 cells), a repeated row is none, and the reader
refuses what it cannot serve faithfully — Fortran order, strided column slices,
out-of-range blocks — rather than returning something plausible.

**`applebee/regions.json` + `datasets.load_registry()`** — the three regions moved
out of the `DATASETS` literal into data. Paths resolve against `data/inputs`
unless absolute; an unknown key raises; `APPLEBEE_REGIONS` names a second file
whose entries extend and override the shipped ones, which is how the acquisition
worker will add coverage without a release. `Dataset` gained `base_url`: when set,
weather is read in ranges, `paths()` is empty and `require()` has nothing to
refuse, because reporting absent local files for a hosted region would mislead.

**`ModelParams` over the wire** — turned out to need nothing. `from_dict()`
already existed with the validation the API needs: unknown keys raise, and lists
coerce back to tuples, so a JSON round-trip through a Lambda is already exact.

End-to-end check: a region defined *only* by a JSON file, read entirely through
ranged reads, produced results identical to the local run over the same 25 cells.

Tests: `tests/test_remote.py`, 12 new; suite 58 → 70, all passing.

**Not done, deliberately.** No AWS account, bucket, or deployment yet — Phase 0
is the code that makes deployment possible, and every piece of it is useful and
tested on a laptop. The one packaging note for later: `regions.json` lives inside
the package directory, so any deployment that copies the package gets it.

## Commits

| SHA | Date | Subject |
|---|---|---|
| `6c48245` | 2026-08-19 | Read weather in byte ranges, and define regions in data |

### Phase 2 — done 2026-08-19

**`applebee/api.py`** — the three answers as plain functions, framework-free and
AWS-free: `parameters()`, `evaluate(params)` and `point(lat, lon, params)`. A
handler turns HTTP into a dict and back; nothing between knows about the cloud.

Warm requests are **2 ms** for a point and 140 ms for a full re-evaluation, once
the grids, the runnable-cell table and the year range are cached per process.
The first cut was 700 ms because `Dataset.model()` re-opened the matrices on
every call and `weather_years()` re-read every input to derive a range; both are
now cached, and that is the entire difference between a cheap endpoint and an
expensive one.

Two behaviours worth recording as decisions rather than details:

- **Caveats are data.** Every payload carries them, and a test asserts it. A
  response that returned R² 0.803 without saying the slope is not significant
  would overstate what the model earned, so it cannot.
- **A point outside the region is refused, not relocated.** The nearest cell to
  Mexico City is 5,155 km away; returning it silently would have been a
  prediction about somewhere else. Past 25 km the answer says which cell
  actually answered; past 500 km it is a 400.

**`web/app.py`** — one routing table serving both a Lambda Function URL and
`python -m web.app` on a laptop, stdlib only. Bad input comes back as a 400
carrying the message `ModelParams` itself raised, so a typo is named rather than
quietly run with a default.

**`web/index.html`** — one page, no build step, no external assets, so it drops
onto S3 as-is and satisfies a strict CSP. The parameter form is generated from
`/api/parameters`, so the page holds no copy of the eighteen numbers. Both panels
run on arrival: every visitor's default request is identical, which is precisely
what the response cache is for.

Tests: `tests/test_api.py`, 21 new, pinning that default parameters still
reproduce the manuscript (R² 0.510 and 0.803, p = 0.358). Suite 70 → 91.

One test failed honestly and was corrected rather than the code: a 25 °C
foraging threshold does *not* zero out reproduction in upstate New York, because
spring there does reach a 25 °C daily mean. The test now asserts what is true —
a stricter threshold can only remove foraging days — and uses 35 °C for the
unreachable case.

### Phase 3 — done 2026-08-19

`api.region()` runs every cell in a region and packs the answer small enough to
send to a browser: coordinates as float32, offspring as uint16 at two decimal
places, base64 in JSON. **1.31 MB for 268,536 values.** A full run is 38.9 s and
reproduces the manuscript exactly — regional mean 14.73, 18 cells that never
accumulate the degree-days to emerge.

`block=(start, stop)` runs one contiguous slice, which is the fan-out: each
worker reads its own rows in a single ranged request and answers for its own
cells. The coordinator merges. Locally, one process runs the lot.

**The cache is the cost model.** Answers are deterministic in (region, years,
parameters), so an identical request replays in **2 ms** instead of 38.9 s. Most
visitors run the defaults, which makes this the difference between a platform
that is free to serve and one that pays for the same 268,536 cell-years over and
over. A local directory now; the same two functions become S3 on deployment.

The map itself is canvas, drawn from the packed arrays, in viridis to match the
manuscript's figures so the page and the paper read as one picture. Clicking it
fills in the coordinates and answers in the location panel rather than growing a
second readout.

One defect worth recording because it was invisible in the numbers: the first
map was **striped**. A cell is 4 km on both sides, but a degree of longitude is
shorter than a degree of latitude at 41°N, so a square dot sized to the
horizontal spacing leaves gaps between the rows. The payload now carries
`cell_degrees` — read off the cells themselves, 1/24° — and the client draws a
cell as a cell. Caught by screenshotting the page, not by a test.

Tests: 6 more in `tests/test_api.py`. Suite 91 → 97.

### Phase 4 — the queue, done 2026-08-19

`applebee/jobs.py` is the only route by which the input data ever changes. A
visitor **requests**, an administrator **approves**, and exactly one worker at a
time carries it out behind a lock. That shape is not caution — PRISM blocks IPs
that fetch concurrently, and a block would take the platform's whole data supply
with it.

Three properties are what the tests actually pin:

- **Two workers can never fetch at once.** The lock is taken before the job is
  chosen, so two workers starting together cannot both decide to fetch. It
  carries a heartbeat, so an 8-hour job is not mistaken for a dead one, and it
  is reclaimable, so a worker that dies does not wedge the queue forever.
- **A request runs nothing.** `POST /api/jobs` returns a queued job and its
  plan; only approval makes it runnable.
- **An unset admin secret fails closed.** With `APPLEBEE_ADMIN_TOKEN` absent,
  approval is refused outright rather than left open.

A job is **planned before it is approved**, without touching the network:
`prism.estimate()` answers "5,114 files, 10.5 GB, about 6.4 hours" — which is
what an administrator needs to know and what a requester rarely guesses. And a
job's `command()` is the existing script, returned rather than reimplemented:
`scripts/fetch_prism.py` is already paced and resumable, so the queue records an
intention to run it rather than keeping a second copy of the fetching logic.

Tests: `tests/test_jobs.py`, 18 new. Suite 97 → 115.

**What is left needs the AWS account**: the Fargate task that claims and runs a
job, the S3 result cache in place of the local directory, and the deployment
itself. Everything above runs and is tested on a laptop.

## Risks

- **PRISM IP block** would halt data supply. Single-worker lock, conservative
  pacing, and resumability (already in `fetch_prism.py`) are the controls.
- **A forecast is a claim.** The paper's own Objective 3 rests on six annual
  counts and is not significant (p = 0.36). A grower-facing number must carry
  that uncertainty visibly, or the platform overstates what the model earned.
- **Scope creep into a general climate tool.** The extent is the Northeast
  because that is where the model was evaluated.

## Follow-ups

- Solar radiation as an egg-production driver (NSRDB, researched 2026-08-19 and
  shelved) would change the model, not the platform — but the platform is where
  such a change would be evaluated most cheaply.
