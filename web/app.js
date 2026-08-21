"use strict";
/* AppleBee's field map.
 *
 * Leaflet supplies the basemap, the panning and the zooming; a canvas pane above
 * the tiles draws the 44,759 model cells. The grid arrives as one packed payload
 * from /api/region -- float32 coordinates and uint16 values, base64 in JSON --
 * because 268,536 numbers as JSON text is several megabytes and as bytes is one.
 */

const $ = (id) => document.getElementById(id);
const fmt = (v, n = 1) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(n);

/* Viridis, sampled from the manuscript's figures so the site and the paper are
   read as one picture. */
const RAMP = [[68,1,84],[72,40,120],[62,74,137],[49,104,142],[38,130,142],
              [31,158,137],[53,183,121],[109,205,89],[180,222,44],[253,231,37]];
function colour(t) {
  const x = Math.max(0, Math.min(1, t)) * 9, i = Math.floor(x), f = x - i;
  const a = RAMP[i], c = RAMP[Math.min(i + 1, 9)];
  return [a[0] + (c[0]-a[0])*f | 0, a[1] + (c[1]-a[1])*f | 0, a[2] + (c[2]-a[2])*f | 0];
}

const state = {grid: null, year: null, values: null, peak: 1,
               mode: "cell", radiusKm: 8, polygon: [], selected: null, params: {}};

/* ---- talking to the model ------------------------------------------- */
async function api(path, body) {
  const options = body ? {method: "POST", headers: {"content-type": "application/json"},
                          body: JSON.stringify(body)} : {};
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({error: response.statusText}));
  if (response.status === 202) return {pending: payload};
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

const unpack = (b64, T) => new T(Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer);

/* ---- the map --------------------------------------------------------- */
const map = L.map("map", {zoomControl: true, preferCanvas: true,
                          minZoom: 4, maxZoom: 13, zoomSnap: .25})
             .setView([42.2, -74.5], 6);

/* A light basemap, so the colour ramp is the only saturated thing on screen and
   a grower can still find their own road. */
L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
               '&copy; <a href="https://carto.com/attributions">CARTO</a> &middot; ' +
               'model: PRISM &amp; USDA CDL, 4 km grid',
  subdomains: "abcd", maxZoom: 19,
}).addTo(map);

// Exposed so an end-to-end check can drive the map the way a person does.
window.__map = map;

const linePane = map.createPane("state-pane");
linePane.style.zIndex = 460;
linePane.style.pointerEvents = "none";
fetch("/states.geojson").then(r => r.json()).then(outlines => {
  state.outlines = outlines;
  L.geoJSON(outlines, {
    pane: "state-pane",
    style: {color: "#3d4a45", weight: 1.1, opacity: .7, fill: false,
            interactive: false},
  }).addTo(map);
}).catch(() => {});   // a missing outline is cosmetic, not fatal

const pane = map.createPane("grid-pane");
pane.style.zIndex = 450;

// Leaflet's own overlay pane sits at 400, below the data canvas at 450, so a
// drawn shape put there is painted over by the grid. Selections get their own
// pane above everything.
const drawPane = map.createPane("draw-pane");
drawPane.style.zIndex = 470;
const canvas = L.DomUtil.create("canvas", "", pane);
const ctx = canvas.getContext("2d");
let dpr = 1;

function sizeCanvas() {
  const size = map.getSize();
  // A stacked layout can lay the map out before it has a height, and
  // createImageData(0, 0) throws rather than drawing nothing.
  if (!size.x || !size.y) return false;
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = size.x * dpr; canvas.height = size.y * dpr;
  canvas.style.width = size.x + "px"; canvas.style.height = size.y + "px";
  const origin = map.containerPointToLayerPoint([0, 0]);
  L.DomUtil.setPosition(canvas, origin);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return true;
}

function drawGrid() {
  const g = state.grid;
  if (!sizeCanvas()) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!g) return;

  /* Cells are drawn from shared edges rather than from a per-cell width, because
     rounding each cell independently leaves hairline gaps between the rows --
     the grid ends up looking striped. The grid is regular, so one x per column
     boundary and one y per row boundary is enough, and neighbours then share an
     edge exactly. */
  const half = g.step / 2;
  const xEdge = new Float64Array(g.cols + 1), yEdge = new Float64Array(g.rows + 1);
  for (let k = 0; k <= g.cols; k++)
    xEdge[k] = map.latLngToContainerPoint([g.lat0, g.lon0 + (k - 0.5) * g.step]).x;
  for (let k = 0; k <= g.rows; k++)
    yEdge[k] = map.latLngToContainerPoint([g.lat0 + (k - 0.5) * g.step, g.lon0]).y;

  const w = canvas.width, h = canvas.height;
  const image = ctx.createImageData(w, h);
  const data = image.data;
  for (let i = 0; i < g.n; i++) {
    const cx = g.gx[i], cy = g.gy[i];
    const x0 = Math.round(xEdge[cx] * dpr), x1 = Math.round(xEdge[cx + 1] * dpr);
    const y1 = Math.round(yEdge[cy] * dpr), y0 = Math.round(yEdge[cy + 1] * dpr);
    if (x1 < 0 || x0 > w || y1 < 0 || y0 > h) continue;
    const [r, gr, bl] = colour((state.values[i] / g.scale) / state.peak);
    for (let y = Math.max(0, y0); y < Math.min(h, Math.max(y1, y0 + 1)); y++) {
      let o = (y * w + Math.max(0, x0)) * 4;
      for (let x = Math.max(0, x0); x < Math.min(w, Math.max(x1, x0 + 1)); x++) {
        data[o] = r; data[o+1] = gr; data[o+2] = bl; data[o+3] = 205;
        o += 4;
      }
    }
  }
  ctx.putImageData(image, 0, 0);
}

map.on("move zoom viewreset resize zoomend moveend", drawGrid);

let resizing = null;
window.addEventListener("resize", () => {
  clearTimeout(resizing);
  resizing = setTimeout(() => { map.invalidateSize(); drawGrid(); }, 120);
});
// The first paint can land before the stacked layout has given the map a
// height, so it is measured again once the browser has settled.
requestAnimationFrame(() => { map.invalidateSize(); drawGrid(); });

/* ---- selection overlays ---------------------------------------------- */
let marker = null, ring = null, sketch = null;
function clearOverlays() {
  for (const layer of [marker, ring, sketch, chosenOutline])
    if (layer) map.removeLayer(layer);
  marker = ring = sketch = chosenOutline = null;
}
function drawSketch() {
  if (sketch) map.removeLayer(sketch);
  sketch = null;
  if (!state.polygon.length) return;

  const points = state.polygon.map(p => [p[1], p[0]]);
  const closed = state.polygon.closed;
  const shape = (style) => closed ? L.polygon(points, style) : L.polyline(points, style);
  sketch = L.layerGroup([
    // A white casing under the line, so it reads against dark purple and bright
    // yellow alike -- one thin stroke vanishes on a viridis map.
    shape({pane: "draw-pane", color: "#ffffff", weight: 6, opacity: .95,
           fill: false, interactive: false}),
    shape({pane: "draw-pane", color: "#1B5E4B", weight: 3, opacity: 1,
           dashArray: closed ? null : "8 5",
           fillColor: "#1B5E4B", fillOpacity: closed ? .18 : 0, interactive: false}),
    ...points.map(p => L.circleMarker(p, {
      pane: "draw-pane", radius: 5.5, color: "#ffffff", weight: 2.5, opacity: 1,
      fillColor: "#1B5E4B", fillOpacity: 1, interactive: false,
    })),
  ]).addTo(map);
}

/* ---- reading the answer ---------------------------------------------- */
function sparkline(points, active) {
  const w = 320, h = 78, pad = {l: 4, r: 4, t: 10, b: 18};
  const max = Math.max(...points.map(p => p.offspring_per_female), 1);
  const X = i => pad.l + i * (w - pad.l - pad.r) / Math.max(1, points.length - 1);
  const Y = v => h - pad.b - (v / max) * (h - pad.t - pad.b);
  const line = points.map((p, i) =>
    `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p.offspring_per_female).toFixed(1)}`).join("");
  const area = `${line}L${X(points.length-1).toFixed(1)},${h-pad.b}L${X(0).toFixed(1)},${h-pad.b}Z`;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img"
    aria-label="Predicted offspring per female by spring">
    <path d="${area}" fill="var(--accent)" opacity=".13"></path>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2"
          stroke-linejoin="round" stroke-linecap="round"></path>
    ${points.map((p, i) => `<circle cx="${X(i)}" cy="${Y(p.offspring_per_female)}"
        r="${p.spring == active ? 4.2 : 2.4}"
        fill="${p.spring == active ? "var(--accent)" : "var(--panel)"}"
        stroke="var(--accent)" stroke-width="1.6"></circle>`).join("")}
    ${points.map((p, i) => `<text x="${X(i)}" y="${h - 5}" text-anchor="middle"
        font-size="9.5" fill="var(--ink-3)"
        font-family="ui-monospace, monospace">${String(p.spring).slice(2)}</text>`).join("")}
  </svg>`;
}

/* Across a drawn area the mean can sit well away from the middle -- the
   distribution is skewed by a handful of very good cells -- so the median and
   the range are shown beside it rather than left to be assumed. */
const day = (iso) => new Date(iso + "T00:00")
  .toLocaleDateString(undefined, {day: "numeric", month: "short"});

/* One driver row: the mean, and under it the range when more than one cell
   contributed to it. */
function driver(label, value, spread, places) {
  return `<dt>${label}</dt><dd class="mono">${fmt(value, places)}
    ${spread ? `<small>${fmt(spread.min, places)} to ${fmt(spread.max, places)}</small>` : ""}</dd>`;
}

function spreadLine(now) {
  const s = now.spread && now.spread.offspring;
  if (!s) return "";
  return `<div class="rank">Across ${now.cells.toLocaleString()} cells:
    <b>${fmt(s.min)}</b> to <b>${fmt(s.max)}</b>, middle cell ${fmt(s.median)}.</div>`;
}

/* The same range, drawn on the ramp, so the width of the spread is seen and not
   only read. */
function band(now) {
  const s = now.spread && now.spread.offspring;
  if (!s) return "";
  const left = Math.max(0, s.min / state.peak * 100);
  const right = Math.min(100, s.max / state.peak * 100);
  return `<u style="left:${left}%; width:${Math.max(1, right - left)}%"></u>`;
}

function show(answer, name) {
  state.selected = {...answer, name};
  const springs = answer.springs;
  if (!springs.length) {
    $("readout").innerHTML = `<div class="empty"><b>No forecast here</b>
      The model could not run at this location.</div>`;
    return;
  }
  const now = springs.find(s => String(s.spring) === String(state.year)) || springs[springs.length - 1];
  const first = springs[0], best = springs.reduce((a, s) =>
    s.offspring_per_female > a.offspring_per_female ? s : a);
  const change = first.offspring_per_female
    ? (now.offspring_per_female - first.offspring_per_female) / first.offspring_per_female * 100 : 0;
  const where = answer.location.description
    || (answer.location.distance_km > 4
        ? `one 4 km cell, ${fmt(answer.location.distance_km, 0)} km away` : "one 4 km cell");
  const context = answer.context || {};

  $("readout").innerHTML = `
    <div>
      <div class="place">${name}
        <small class="mono">${fmt(answer.location.requested.lat, 3)}°N,
          ${fmt(Math.abs(answer.location.requested.lon), 3)}°W &middot; ${where}</small>
      </div>
    </div>
    <div>
      <div class="headline">
        <b class="mono">${fmt(now.offspring_per_female)}</b>
        <span>offspring per female<br>expected in <b>spring ${now.spring}</b></span>
      </div>
      ${spreadLine(now)}
      ${context.percentile !== undefined ? `<div class="rank">Higher than
        <b>${fmt(context.percentile, 0)}%</b> of the Northeast
        (regional average ${fmt(context.regional_mean)}).
        <div class="bar">${band(now)}<i style="left:${Math.min(99,
          now.offspring_per_female / state.peak * 100)}%"></i></div></div>` : ""}
    </div>
    <div>
      <label class="lab">Season by season</label>
      ${sparkline(springs, now.spring)}
      <div class="rank" style="margin-top:2px">
        ${change >= 0 ? "Up" : "Down"} <b>${fmt(Math.abs(change), 0)}%</b>
        since spring ${first.spring}, best in <b>${best.spring}</b>.
      </div>
    </div>
    <div>
      <div class="actions">
        <button id="export">Export this report</button>
      </div>
    </div>
    <div>
      <label class="lab">What shaped ${now.spring}</label>
      <dl class="drivers">
        ${driver("Eggs laid per female", now.eggs_per_female, now.spread?.eggs, 1)}
        ${driver("Days too cold to forage", now.days_lost_to_cold,
                 now.spread?.days_lost_to_cold, 0)}
        ${driver("Days rained off", now.days_lost_to_rain,
                 now.spread?.days_lost_to_rain, 0)}
        ${driver("Spring forage nearby", now.forage_index, now.spread?.forage_index, 2)}
        <dt>Bees emerged</dt><dd class="mono">${day(now.emergence_date)}
          ${now.spread ? `<small>${day(now.spread.emergence.earliest)} to
             ${day(now.spread.emergence.latest)}</small>` : ""}</dd>
      </dl>
    </div>`;

  $("export").onclick = () => report(now);

}

/* ---- the report ------------------------------------------------------ */
const sheet = $("sheet");
function report(now) {
  const answer = state.selected, springs = answer.springs;
  const context = answer.context || {};
  const emerged = s => new Date(s.emergence_date + "T00:00")
    .toLocaleDateString(undefined, {day: "numeric", month: "short"});

  $("sheet-body").innerHTML = `
    <h2 id="sheet-title">${answer.name}</h2>
    <p class="sub">${fmt(answer.location.requested.lat, 3)}°N,
      ${fmt(Math.abs(answer.location.requested.lon), 3)}°W &middot;
      ${answer.location.description || "one 4 km cell"} &middot; AppleBee forecast</p>

    <h3>Expected in spring ${now.spring}</h3>
    <table><tbody>
      <tr><td>Offspring per female${now.spread ? ", average" : ""}</td>
        <td><b>${fmt(now.offspring_per_female)}</b></td></tr>
      ${now.spread ? `
      <tr><td>Across ${now.cells.toLocaleString()} cells</td>
        <td>${fmt(now.spread.offspring.min)} to ${fmt(now.spread.offspring.max)}</td></tr>
      <tr><td>Middle cell</td><td>${fmt(now.spread.offspring.median)}</td></tr>` : ""}
      <tr><td>Eggs laid per female</td><td>${fmt(now.eggs_per_female)}</td></tr>
      <tr><td>Bees emerged</td><td>${emerged(now)}${now.spread
        ? ` (${emerged({emergence_date: now.spread.emergence.earliest})} to ${
            emerged({emergence_date: now.spread.emergence.latest})})` : ""}</td></tr>
      ${context.percentile !== undefined ? `<tr><td>Compared with the Northeast</td>
        <td>higher than ${fmt(context.percentile, 0)}% of cells</td></tr>` : ""}
    </tbody></table>

    <h3>Season by season</h3>
    <table>
      <thead><tr><th>Spring</th><th>Offspring per female</th>
        ${springs[0].spread ? "<th>Range</th>" : ""}<th>Emerged</th>
        <th>Cold days</th><th>Wet days</th></tr></thead>
      <tbody>${springs.map(s => `<tr><td>${s.spring}</td>
        <td>${fmt(s.offspring_per_female)}</td>
        ${s.spread ? `<td>${fmt(s.spread.offspring.min)}&ndash;${
          fmt(s.spread.offspring.max)}</td>` : ""}
        <td>${emerged(s)}</td>
        <td>${fmt(s.days_lost_to_cold, 0)}</td>
        <td>${fmt(s.days_lost_to_rain, 0)}</td></tr>`).join("")}</tbody>
    </table>

    <p class="fine">AppleBee models the wild mason bee <i>Osmia cornifrons</i> from
      PRISM weather and the USDA Cropland Data Layer on a 4 km grid. Treat it as
      guidance for planning, not as a count of the bees in your orchard.</p>

    <footer>
      <button class="ghost" id="sheet-close">Close</button>
      <button id="sheet-print">Print or save as PDF</button>
    </footer>`;
  sheet.setAttribute("open", "");
  $("sheet-close").onclick = () => sheet.removeAttribute("open");
  $("sheet-print").onclick = () => window.print();
}
sheet.addEventListener("click", e => { if (e.target === sheet) sheet.removeAttribute("open"); });
document.addEventListener("keydown", e => { if (e.key === "Escape") sheet.removeAttribute("open"); });

/* ---- asking ---------------------------------------------------------- */
function busy(message) {
  $("readout").innerHTML = `<div class="empty"><b><span class="busy"></span> ${message}</b>
    The model is running for this location.</div>`;
}
function failed(error) {
  $("readout").innerHTML = `<div class="empty"><b>That did not work</b>${error.message}</div>`;
}

async function askPoint(lat, lon, name) {
  busy("Working…");
  clearOverlays();
  marker = L.layerGroup([
    L.circleMarker([lat, lon], {pane: "draw-pane", radius: 8, color: "#ffffff",
                                weight: 5, fill: false}),
    L.circleMarker([lat, lon], {pane: "draw-pane", radius: 8, color: "#1B5E4B",
                                weight: 3, fillColor: "#1B5E4B", fillOpacity: .6}),
  ]).addTo(map);
  try {
    const answer = await api(`/api/point?lat=${lat}&lon=${lon}`);
    show(answer, name || `${lat.toFixed(2)}°N, ${Math.abs(lon).toFixed(2)}°W`);
  } catch (error) { failed(error); }
}

async function askRadius(lat, lon, name) {
  busy("Averaging the area…");
  clearOverlays();
  ring = L.layerGroup([
    L.circle([lat, lon], {pane: "draw-pane", radius: state.radiusKm * 1000,
                          color: "#ffffff", weight: 6, opacity: .95, fill: false}),
    L.circle([lat, lon], {pane: "draw-pane", radius: state.radiusKm * 1000,
                          color: "#1B5E4B", weight: 3, fillColor: "#1B5E4B",
                          fillOpacity: .16}),
  ]).addTo(map);
  try {
    const answer = await api("/api/area", {lat, lon, radius_km: state.radiusKm,
                                           parameters: state.params});
    show(answer, name || `Within ${state.radiusKm} km`);
  } catch (error) { failed(error); }
}

async function askPolygon() {
  busy("Averaging the area…");
  try {
    const answer = await api("/api/area", {polygon: state.polygon, parameters: state.params});
    show(answer, "Drawn area");
    $("draw-hint").textContent = `${answer.location.cells} cells inside the shape.`;
  } catch (error) {
    failed(error);
    $("draw-hint").textContent = error.message;
  }
}

map.on("click", e => {
  const {lat, lng} = e.latlng;
  if (state.mode === "poly") {
    if (state.polygon.closed) state.polygon = [];
    state.polygon.push([lng, lat]);
    drawSketch();
    $("draw-hint").textContent = state.polygon.length < 3
      ? `${state.polygon.length} corner${state.polygon.length === 1 ? "" : "s"}. At least three.`
      : `${state.polygon.length} corners. Close the shape when it is right.`;
    return;
  }
  if (state.mode === "area") askRadius(lat, lng);
  else askPoint(lat, lng);
});

/* Hovering reads the packed grid directly, so it costs no request. */
const tip = $("tip");
map.on("mousemove", e => {
  const g = state.grid;
  if (!g) return;
  const i = nearestCell(e.latlng.lat, e.latlng.lng);
  if (i < 0) { tip.style.opacity = 0; return; }
  const p = map.latLngToContainerPoint(e.latlng);
  tip.style.opacity = 1;
  tip.style.left = (p.x + 15) + "px"; tip.style.top = (p.y + 15) + "px";
  tip.innerHTML = `<b>${fmt(state.values[i] / g.scale)}</b> offspring per female`;
});
map.on("mouseout", () => { tip.style.opacity = 0; });

function nearestCell(lat, lon) {
  const g = state.grid;
  let best = -1, far = g.step * g.step * 2;
  for (let i = 0; i < g.n; i++) {
    const dy = g.lat[i] - lat, dx = (g.lon[i] - lon) * 0.75;
    const d = dx * dx + dy * dy;
    if (d < far) { far = d; best = i; }
  }
  return best;
}

/* ---- search ---------------------------------------------------------- */
const matches = $("matches");
let searching = null;
async function search() {
  const query = $("q").value.trim();
  if (query.length < 2) return;
  $("hint").innerHTML = '<span class="busy"></span> Looking that up…';
  try {
    const found = await api(`/api/places?q=${encodeURIComponent(query)}`);
    if (!found.places.length) {
      $("hint").textContent = `Nothing found for “${query}”. Try a town and state.`;
      matches.removeAttribute("open");
      return;
    }
    $("hint").textContent = "Or click anywhere on the map.";
    matches.innerHTML = found.places.map((p, i) =>
      `<button data-i="${i}" role="option">${p.name}</button>`).join("");
    matches.setAttribute("open", "");
    matches.onclick = e => {
      const button = e.target.closest("button");
      if (!button) return;
      const place = found.places[+button.dataset.i];
      matches.removeAttribute("open");
      $("q").value = place.name.split(",")[0];
      map.setView([place.lat, place.lon], 10);
      if (state.mode === "area") askRadius(place.lat, place.lon, place.name.split(",")[0]);
      else askPoint(place.lat, place.lon, place.name.split(",")[0]);
    };
  } catch (error) { $("hint").textContent = error.message; }
}
$("go").onclick = search;
$("q").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
$("q").addEventListener("input", () => {
  clearTimeout(searching);
  if ($("q").value.trim().length >= 3) searching = setTimeout(search, 450);
});
document.addEventListener("click", e => {
  if (!e.target.closest(".searchbox")) matches.removeAttribute("open");
});

/* ---- modes ----------------------------------------------------------- */
const MODES = {cell: "m-cell", area: "m-area", poly: "m-poly", state: "m-state"};
function setMode(next) {
  state.mode = next;
  for (const [key, id] of Object.entries(MODES))
    $(id).setAttribute("aria-pressed", String(key === next));
  $("radius-row").hidden = next !== "area";
  $("draw-row").hidden = next !== "poly";
  $("state-row").hidden = next !== "state";
  if (next !== "poly") { state.polygon = []; drawSketch(); }
}
for (const [key, id] of Object.entries(MODES)) $(id).onclick = () => setMode(key);

$("radius").oninput = () => {
  state.radiusKm = +$("radius").value;
  $("radius-out").textContent = state.radiusKm + " km";
};
$("radius").onchange = () => {
  if (state.selected && state.mode === "area")
    askRadius(state.selected.location.requested.lat, state.selected.location.requested.lon);
};
$("draw-undo").onclick = () => {
  state.polygon.pop(); state.polygon.closed = false; drawSketch();
  $("draw-hint").textContent = state.polygon.length
    ? `${state.polygon.length} corners.` : "Click the map to place corners.";
};
$("draw-clear").onclick = () => {
  state.polygon = []; drawSketch();
  $("draw-hint").textContent = "Click the map to place corners.";
};
$("draw-close").onclick = () => {
  if (state.polygon.length < 3) {
    $("draw-hint").textContent = "A shape needs at least three corners.";
    return;
  }
  state.polygon.closed = true; drawSketch(); askPolygon();
};

/* ---- the whole grid, as a file ---------------------------------------- */
$("download").onclick = async function () {
  this.disabled = true;
  const was = this.textContent;
  this.innerHTML = '<span class="busy"></span> Preparing…';
  try {
    const years = state.grid.springs.join(",");
    const answer = await api(`/api/download?years=${years}`);
    const url = URL.createObjectURL(new Blob([answer.csv], {type: "text/csv"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = `applebee_northeast_${state.grid.springs[0]}-${
      state.grid.springs[state.grid.springs.length - 1]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    $("download-hint").textContent =
      `${state.grid.n.toLocaleString()} cells \u00D7 ${state.grid.springs.length} seasons, ` +
      "one row per cell.";
  } catch (error) {
    $("download-hint").textContent = error.message;
  } finally { this.disabled = false; this.textContent = was; }
};

/* ---- whole states ---------------------------------------------------- */
async function loadStates() {
  const answer = await api("/api/states");
  if (!answer.states.length) { $("m-state").hidden = true; return; }
  $("state-list").innerHTML = answer.states.map(s => `
    <label><input type="checkbox" value="${s.name}">
      ${s.name}<small>${s.cells.toLocaleString()}</small></label>`).join("");
  $("state-list").addEventListener("change", askStates);
  $("state-all").onclick = () => { setAllStates(true); askStates(); };
  $("state-none").onclick = () => { setAllStates(false); clearOverlays(); };
}

function setAllStates(on) {
  for (const box of document.querySelectorAll("#state-list input")) box.checked = on;
}

function chosenStates() {
  return [...document.querySelectorAll("#state-list input:checked")].map(b => b.value);
}

async function askStates() {
  const chosen = chosenStates();
  if (!chosen.length) return;
  busy(chosen.length === 1 ? `Averaging ${chosen[0]}\u2026`
                           : `Averaging ${chosen.length} states\u2026`);
  clearOverlays();
  highlightStates(chosen);
  try {
    const answer = await api("/api/area", {states: chosen, parameters: state.params});
    show(answer, chosen.length === 1 ? chosen[0] : `${chosen.length} states`);
  } catch (error) { failed(error); }
}

/* The chosen states are outlined on the map, so the selection is visible there
   and not only in the list. */
let chosenOutline = null;
function highlightStates(names) {
  if (chosenOutline) { map.removeLayer(chosenOutline); chosenOutline = null; }
  if (!state.outlines) return;
  const wanted = new Set(names);
  chosenOutline = L.geoJSON(state.outlines, {
    pane: "draw-pane",
    filter: f => wanted.has(f.properties.NAME),
    style: {color: "#1B5E4B", weight: 2.5, fillColor: "#1B5E4B", fillOpacity: .14,
            interactive: false},
  }).addTo(map);
}

/* ---- parameters ------------------------------------------------------ */
const GROUPS = [
  ["Emergence", ["emergence_base_temp", "emergence_thermal_constant", "emergence_start_doy"]],
  ["Egg production", ["mating_days", "longevity", "temperature_threshold",
                      "precipitation_threshold", "forage_threshold",
                      "eggs_high_forage", "eggs_low_forage"]],
  ["Egg and larva mortality", ["egg_larva_days", "mortality_factor",
                               "lower_dev_threshold", "upper_dev_threshold"]],
  ["Winter mortality", ["prewinter_start", "prewinter_end",
                        "diapause_temp_threshold", "winter_mortality_factor"]],
];

function renderParameters(spec) {
  const byName = Object.fromEntries(spec.parameters.map(f => [f.name, f]));
  $("param-groups").innerHTML = GROUPS.map(([title, names]) => `
    <div class="pgroup"><b>${title}</b>
      <div class="params">${names.map(name => {
        const f = byName[name];
        if (!f) return "";
        const value = Array.isArray(f.default) ? f.default.join(" / ") : f.default;
        return `<div><label>${f.description}
            <span style="color:var(--ink-3)">${f.unit || ""}</span></label>
          <input type="${f.type === "date" ? "text" : "number"}" step="any"
                 value="${value}" data-name="${name}" data-default="${value}"
                 ${f.type === "date" ? "disabled" : ""}>
          <label style="margin-top:3px; color:var(--ink-3); font-size:10px">${f.source}</label>
        </div>`;
      }).join("")}</div>
    </div>`).join("");
}

function changedParameters() {
  const changed = {};
  for (const input of document.querySelectorAll("#param-groups input")) {
    if (input.disabled || input.value === input.dataset.default) continue;
    const value = Number(input.value);
    if (Number.isFinite(value)) changed[input.dataset.name] = value;
  }
  return changed;
}

$("param-reset").onclick = () => {
  for (const input of document.querySelectorAll("#param-groups input"))
    input.value = input.dataset.default;
  state.params = {};
};
$("param-run").onclick = async function () {
  state.params = changedParameters();
  const count = Object.keys(state.params).length;
  this.disabled = true;
  this.textContent = count ? `Recalculating ${count} change${count === 1 ? "" : "s"}…`
                           : "Recalculating…";
  try {
    await loadGrid();
    if (state.selected) {
      const {lat, lon} = state.selected.location.requested;
      if (state.mode === "area") await askRadius(lat, lon, state.selected.name);
      else await askPoint(lat, lon, state.selected.name);
    }
    this.textContent = "Recalculate the region";
  } catch (error) {
    this.textContent = "Try again";
  } finally { this.disabled = false; }
};

/* ---- the grid -------------------------------------------------------- */
async function loadGrid() {
  const answer = await pollRegion();
  const lon = unpack(answer.lon, Float32Array), lat = unpack(answer.lat, Float32Array);
  const step = answer.cell_degrees || 1/24;
  let lon0 = Infinity, lat0 = Infinity;
  for (let i = 0; i < lon.length; i++) {
    if (lon[i] < lon0) lon0 = lon[i];
    if (lat[i] < lat0) lat0 = lat[i];
  }
  // Column and row of every cell, so a redraw is integer lookups rather than
  // 45,000 projections.
  const gx = new Uint16Array(lon.length), gy = new Uint16Array(lon.length);
  let cols = 0, rows = 0;
  for (let i = 0; i < lon.length; i++) {
    gx[i] = Math.round((lon[i] - lon0) / step);
    gy[i] = Math.round((lat[i] - lat0) / step);
    if (gx[i] > cols) cols = gx[i];
    if (gy[i] > rows) rows = gy[i];
  }
  const g = {
    n: answer.cells, step, scale: answer.encoding.scale,
    lon, lat, gx, gy, lon0, lat0, cols: cols + 1, rows: rows + 1,
    years: Object.fromEntries(Object.entries(answer.by_spring)
      .map(([k, v]) => [k, unpack(v, Uint16Array)])),
    springs: answer.springs,
  };
  state.grid = g;
  state.peak = answer.summary.max;
  if (!state.year || !g.years[state.year]) state.year = String(g.springs[g.springs.length - 1]);
  state.values = g.years[state.year];

  $("year-row").innerHTML = g.springs.map(s =>
    `<button class="ghost" data-year="${s}" aria-pressed="${String(s) === state.year}">${s}</button>`).join("");
  $("leg-max").textContent = Math.round(state.peak);
  $("leg-year").textContent = "spring " + state.year;
  drawGrid();
}

async function pollRegion() {
  for (let attempt = 0; attempt < 60; attempt++) {
    const answer = await api("/api/region", {parameters: state.params});
    if (!answer.pending) return answer;
    // A first run under new parameters takes a minute, and the page should not
    // look broken while it does.
    $("leg-year").innerHTML = '<span class="busy"></span> building the map';
    if (!$("year-row").children.length) {
      $("year-row").innerHTML = '<span class="empty">Seasons appear when the map does.</span>';
    }
    await new Promise(done => setTimeout(done, 5000));
  }
  throw new Error("The regional run is taking longer than expected.");
}

$("year-row").addEventListener("click", e => {
  const button = e.target.closest("button");
  if (!button) return;
  state.year = button.dataset.year;
  state.values = state.grid.years[state.year];
  [...$("year-row").children].forEach(c => c.setAttribute("aria-pressed", String(c === button)));
  $("leg-year").textContent = "spring " + state.year;
  drawGrid();
  if (state.selected) show(state.selected, state.selected.name);
});

/* ---- go -------------------------------------------------------------- */
api("/api/parameters").then(renderParameters).catch(() => {});
loadStates().catch(() => { $("m-state").hidden = true; });
loadGrid().catch(error => {
  $("leg-year").textContent = "unavailable";
  $("readout").innerHTML = `<div class="empty"><b>The map could not load</b>${error.message}</div>`;
});
