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
``POST /api/region``             every cell in a region, packed
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee import api  # noqa: E402

STATIC = Path(__file__).resolve().parent
INDEX = STATIC / "index.html"

# Answers are deterministic in their inputs, so a shared cache is free to use.
# The platform's cost model depends on it: identical requests are the common
# case, and each one served from cache is compute not spent.
CACHE_SECONDS = 3600


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def route(method: str, path: str, query: dict, body: dict | None) -> tuple[int, dict]:
    """Answer one request. Pure, so the tests never start a server."""
    body = body or {}
    if path == "/api/parameters" and method == "GET":
        return 200, api.parameters()
    if path == "/api/provenance" and method == "GET":
        return 200, api.provenance()
    if path == "/api/evaluate" and method in ("GET", "POST"):
        return 200, api.evaluate(body.get("parameters"))
    if path == "/api/region" and method in ("GET", "POST"):
        block = body.get("block")
        return 200, api.region(body.get("parameters"),
                               region=body.get("region", query.get("region",
                                                                   api.DEFAULT_REGION)),
                               years=body.get("years"),
                               block=tuple(block) if block else None)
    if path == "/api/point" and method in ("GET", "POST"):
        lat = _number(body.get("lat", query.get("lat")), "lat")
        lon = _number(body.get("lon", query.get("lon")), "lon")
        years = body.get("years")
        region = body.get("region", query.get("region", api.DEFAULT_REGION))
        return 200, api.point(lat, lon, body.get("parameters"),
                              region=region, years=years)
    raise HttpError(404, f"no route for {method} {path}")


def answer(method: str, path: str, query: dict, body: dict | None) -> tuple[int, dict]:
    """:func:`route`, with every failure turned into a status and a message."""
    try:
        return route(method, path, query, body)
    except HttpError as exc:
        return exc.status, {"error": exc.message}
    except (ValueError, TypeError, KeyError) as exc:
        # ModelParams raises ValueError naming the unknown keys; an unknown
        # region raises KeyError listing the alternatives. Both are useful.
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

    raw = event.get("body")
    if raw and event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        status, payload = 400, {"error": f"body is not JSON: {exc}"}
    else:
        status, payload = answer(method, path, query, body)

    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": f"public, max-age={CACHE_SECONDS}" if status == 200 else "no-store",
        },
        "body": json.dumps(payload, default=str),
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
        self._json(*answer("GET", parsed.path, query, None))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length).decode() if length else ""
        parsed = urlparse(self.path)
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            return self._json(400, {"error": f"body is not JSON: {exc}"})
        self._json(*answer("POST", parsed.path, {}, body))

    def _static(self, path: str) -> None:
        target = INDEX if path in ("/", "/index.html") else STATIC / path.lstrip("/")
        if not target.is_file() or STATIC not in target.resolve().parents:
            return self._json(404, {"error": f"no such page {path}"})
        kind = {".html": "text/html", ".js": "text/javascript",
                ".css": "text/css"}.get(target.suffix, "application/octet-stream")
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


def serve(port: int = 8000) -> None:
    print(f"AppleBee on http://127.0.0.1:{port}  (ctrl-c to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), _Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    serve(parser.parse_args().port)
