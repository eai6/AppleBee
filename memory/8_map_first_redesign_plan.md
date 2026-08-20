# 8 — Map-first redesign

**Date:** 2026-08-20
**Purpose:** Rebuild the platform around the map, for growers rather than
reviewers. Modelled on Beescape (beescape.psu.edu), which solves the same
problem for the same audience.

## Context

Plan 7 shipped a working platform at
<https://wy3vnrdipv.us-east-1.awsapprunner.com>: three stacked cards on a
scrolling page — a location panel taking latitude and longitude as numbers, the
paper's two evaluations, and eighteen parameter fields.

That is a **reviewer's** layout, and it was the right first build: it made the
model's claims checkable. But the stated goal is growers, and a grower does not
have a latitude, does not need R² and p, and will never change
`emergence_thermal_constant`. The page asks them to read a paper before it will
tell them anything.

Beescape is the proof that the other shape works: a full-bleed map, an address
box, floating panels, and no statistics until you ask for them.

## What changes

| Now | After |
|---|---|
| Map inside a card, static | **The map is the page**, pan and zoom |
| Latitude and longitude as numbers | **Address search**, or click the map |
| Two evaluations, R², β, p, ICC | **Gone from the main view** |
| Six springs in a table | **One number for the latest year**, series below |
| Eighteen parameters always visible | **Advanced drawer, closed** |
| One scrolling column | **Left panel, map, right panel** |

Nothing is removed from the API. `/api/evaluate` still answers, and the
parameter form still works — they stop being the first thing a visitor meets.

## Layout

Beescape's arrangement, which is the right one:

```
+----------------------------------------------------------+
| [logo]                                    [ AppleBee ]   |  floating, over map
|  +----------------+                    +--------------+  |
|  | search address |                    | Adams County |  |
|  | [ ] point  [ ] |                    | 14.7 offspring per female
|  |  radius ---o-- |                    | spring 2026  |
|  +----------------+                    |              |
|  | year   2026 v  |                    | [sparkline]  |
|  | layer  offspr. |                    | 2014 ... 2026|
|  +----------------+                    |              |
|                                        | what drove it|
|         [ the map, full bleed ]        | 3 cold days  |
|                                        | 2 wet days   |
|                                        | forage 0.47  |
|  [+/-]                                 +--------------+
|  [ advanced settings v ]                                 |
+----------------------------------------------------------+
```

- **Left, floating**: search, selection mode (a cell, or a radius around a
  point), the year, and the layer being coloured. Advanced settings live at the
  bottom, closed.
- **Centre**: the map, edge to edge, with a real basemap so a grower can find
  their own orchard by its roads.
- **Right, floating**: what the selected place predicts. Empty until something
  is selected, and it says so rather than showing zeros.

## Decisions to make

1. **Map engine.** Leaflet (42 KB, no key) with the grid drawn to a canvas
   overlay, reusing the packed payload and drawing code that already works.
   MapLibre is smoother but 800 KB, and its advantage is a vector basemap we do
   not need.
2. **Basemap.** A light grey canvas, as Beescape uses, so the colour ramp is the
   only saturated thing on screen. Carto Positron or Esri Light Gray, both free
   at this scale, both needing attribution.
3. **Geocoding.** Nominatim is free and adequate at this traffic, but its policy
   wants a real User-Agent and no hammering — so it is proxied through
   `/api/geocode` where the header can be set and answers cached, rather than
   called from the browser.
4. **"Latest year" is a moving target.** Springs run to 2019 today and 2026 once
   the backfill lands. The interface names the year rather than saying "latest".
5. **A group of cells.** Beescape offers a radius and a polygon. A radius is
   enough here and needs one new endpoint that averages the cells inside it.

## Open questions

1. Is the right-hand panel's headline **offspring per female** — the model's own
   quantity — or something a grower reads more directly, like a percentile
   against the region ("better than 72% of the Northeast")?
2. Does the map colour offspring only, or also its drivers (forage, cold days),
   the way Beescape lets you switch habitat factors?
3. Keep a link to the reviewer view, or drop it from the site entirely?
