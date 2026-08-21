"""HTTP in front of :mod:`applebee.api`, for Lambda and for a laptop.

The routing table is a plain function of ``(method, path, query, body)``, so the
same code answers a Lambda Function URL event and a ``python -m web.app`` server
on localhost. Nothing here knows anything about the model: it parses, calls
:mod:`applebee.api`, and serialises.

    python -m web.app                 # http://127.0.0.1:8000
    python -m web.app --port 9000

Endpoints:

===============================  ==========================================
``GET  /api/parameters``         the parameter set, defaults and provenance
``POST /api/evaluate``           the paper's two evaluations under a set
``GET  /api/point?lat=&lon=``    one location, year by year
``POST /api/point``              the same, with parameters in the body
``GET  /api/places?q=``          addresses and towns, for the search box
``POST /api/area``               a radius or a drawn shape, averaged
``GET  /api/states``             the states this region covers
``GET  /api/download?years=``    every cell, every chosen spring, as CSV
``POST /api/region``             every cell in a region, packed
``GET  /api/jobs``               the extension queue
``POST /api/jobs``               request that the inputs be extended
``POST /api/jobs/{id}/approve``  approve one — administrators only
``GET  /api/provenance``         where the inputs came from
===============================  ==========================================

Bad parameters come back as 400 with the message ``ModelParams`` raised, so a
typo in a request is reported rather than silently run with a default.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee import api  # noqa: E402

STATIC = Path(__file__).resolve().parent
INDEX = STATIC / "index.html"

CONTENT_TYPES = {".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".geojson": "application/geo+json"}

# Answers are deterministic in their inputs, so a shared cache is free to use.
# The platform's cost model depends on it: identical requests are the common
# case, and each one served from cache is compute not spent.
CACHE_SECONDS = 3600


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def route(method: str, path: str, query: dict, body: dict | None,
          headers: dict | None = None) -> tuple[int, dict]:
    """Answer one request. Pure, so the tests never start a server."""
    body = body or {}
    headers = headers or {}
    if path == "/api/parameters" and method == "GET":
        return 200, api.parameters()
    if path == "/api/jobs" and method == "GET":
        return 200, api.jobs(query.get("state"))
    if path == "/api/jobs" and method == "POST":
        kind = body.get("kind")
        if not kind:
            raise HttpError(400, "kind is required: 'weather' or 'forage'")
        return 200, api.request_job(kind, requested_by=body.get("requested_by", ""),
                                    **body.get("parameters", {}))
    if path.startswith("/api/jobs/") and path.endswith("/approve") and method == "POST":
        job_id = path.split("/")[3]
        return 200, api.approve_job(job_id, token=_admin_token(body, headers),
                                    by=body.get("by", ""))
    if path == "/api/provenance" and method == "GET":
        return 200, api.provenance()
    if path == "/api/evaluate" and method in ("GET", "POST"):
        return 200, api.evaluate(body.get("parameters"))
    if path == "/api/region" and method in ("GET", "POST"):
        return _region(body, query)
    if path == "/api/places" and method == "GET":
        return 200, api.places(query.get("q", ""))
    if path == "/api/area" and method == "POST":
        return 200, api.area(body.get("parameters"),
                             region=body.get("region", api.DEFAULT_REGION),
                             lat=body.get("lat"), lon=body.get("lon"),
                             radius_km=body.get("radius_km"),
                             polygon=body.get("polygon"),
                             chosen_states=body.get("states"),
                             years=body.get("years"))
    if path == "/api/states" and method == "GET":
        return 200, api.states(query.get("region", api.DEFAULT_REGION))
    if path == "/api/download" and method == "GET":
        years = [int(y) for y in query.get("years", "").split(",") if y.strip()]
        return 200, {"csv": api.download(region=query.get("region", api.DEFAULT_REGION),
                                         years=years or None)}
    if path == "/api/point" and method in ("GET", "POST"):
        lat = _number(body.get("lat", query.get("lat")), "lat")
        lon = _number(body.get("lon", query.get("lon")), "lon")
        years = body.get("years")
        region = body.get("region", query.get("region", api.DEFAULT_REGION))
        return 200, api.point(lat, lon, body.get("parameters"),
                              region=region, years=years)
    raise HttpError(404, f"no route for {method} {path}")


# A region run is 268,536 cell-years and takes rather longer than any HTTP
# request should, so it is never done inside one: a miss starts the work and
# says so, and the caller asks again. The answer lands in the shared cache, so
# whoever asks next gets it whether or not they were the one who started it.
_running: set[str] = set()
_running_lock = threading.Lock()


def _region(body: dict, query: dict) -> tuple[int, dict]:
    settings = {"region": body.get("region", query.get("region", api.DEFAULT_REGION)),
                "years": body.get("years")}
    parameters = body.get("parameters")

    block = body.get("block")
    if block:                       # a worker's slice: small, and answered inline
        return 200, api.region(parameters, block=tuple(block), **settings)

    key = api.region_key(parameters, **settings)
    ready = api.cached_region(key)
    if ready is not None:
        return 200, ready

    with _running_lock:
        already = key in _running
        _running.add(key)
    if not already:
        threading.Thread(target=_compute, args=(key, parameters, settings),
                         daemon=True).start()
    return 202, {"status": "running", "key": key, "retry_after_seconds": 20,
                 "note": ("Running 268,536 cell-years under these parameters. "
                          "Ask again in a moment; the answer is kept, so this "
                          "happens once per parameter set.")}


def _compute(key: str, parameters, settings: dict) -> None:
    try:
        api.region(parameters, **settings)
    except Exception:               # noqa: BLE001 -- logged; the caller retries
        traceback.print_exc()
    finally:
        with _running_lock:
            _running.discard(key)


def _admin_token(body: dict, headers: dict) -> str | None:
    """The token from the header if present, the body otherwise."""
    lowered = {k.lower(): v for k, v in headers.items()}
    return lowered.get("x-admin-token") or body.get("token")


def answer(method: str, path: str, query: dict, body: dict | None,
           headers: dict | None = None) -> tuple[int, dict]:
    """:func:`route`, with every failure turned into a status and a message."""
    try:
        return route(method, path, query, body, headers)
    except HttpError as exc:
        return exc.status, {"error": exc.message}
    except PermissionError as exc:
        return 403, {"error": str(exc)}
    except (ValueError, TypeError, KeyError) as exc:
        # ModelParams raises ValueError naming the unknown keys; an unknown
        # region raises KeyError listing the alternatives. Both are useful to a
        # caller -- but the traceback is only useful in the log, and a 400
        # without one made a deployment failure take far longer to find than it
        # should have.
        traceback.print_exc()
        return 400, {"error": str(exc).strip("'")}


def _number(value, name: str) -> float:
    if value is None:
        raise HttpError(400, f"{name} is required")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HttpError(400, f"{name} must be a number, got {value!r}") from None


# ---------------------------------------------------------------------------
# AWS Lambda
# ---------------------------------------------------------------------------


def handler(event: dict, context=None) -> dict:
    """Entry point for a Lambda Function URL (payload format 2.0)."""
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")
    query = {k: v for k, v in (event.get("queryStringParameters") or {}).items()}

    if not path.startswith("/api/"):
        return _page(path)

    raw = event.get("body")
    if raw and event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        status, payload = 400, {"error": f"body is not JSON: {exc}"}
    else:
        status, payload = answer(method, path, query, body, event.get("headers") or {})

    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": f"public, max-age={CACHE_SECONDS}" if status == 200 else "no-store",
        },
        "body": json.dumps(payload, default=str),
    }


def _page(path: str) -> dict:
    """The single-page app, served by the same function as the API.

    One Function URL answers everything, so the first deployment needs no second
    bucket and no distribution. A CDN goes in front later without moving it.
    """
    target = INDEX if path in ("/", "/index.html") else STATIC / path.lstrip("/")
    if not target.is_file() or STATIC not in target.resolve().parents:
        return {"statusCode": 404, "headers": {"content-type": "application/json"},
                "body": json.dumps({"error": f"no such page {path}"})}
    return {
        "statusCode": 200,
        "headers": {"content-type": CONTENT_TYPES.get(target.suffix, "text/html; charset=utf-8"),
                    "cache-control": "public, max-age=300"},
        "body": target.read_text(),
    }


# ---------------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return self._static(parsed.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self._json(*answer("GET", parsed.path, query, None, dict(self.headers)))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length).decode() if length else ""
        parsed = urlparse(self.path)
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            return self._json(400, {"error": f"body is not JSON: {exc}"})
        self._json(*answer("POST", parsed.path, {}, body, dict(self.headers)))

    def _static(self, path: str) -> None:
        target = INDEX if path in ("/", "/index.html") else STATIC / path.lstrip("/")
        if not target.is_file() or STATIC not in target.resolve().parents:
            return self._json(404, {"error": f"no such page {path}"})
        kind = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), kind)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, default=str).encode(), "application/json")

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"  {self.command} {self.path} -> {args[1]}\n")


def serve(port: int = 8000, host: str = "127.0.0.1") -> None:
    print(f"AppleBee on http://{host}:{port}  (ctrl-c to stop)")
    ThreadingHTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1",
                        help="0.0.0.0 to accept connections from outside")
    args = parser.parse_args()
    serve(args.port, args.host)
