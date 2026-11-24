"""SurrealDB over HTTP RPC. Root for migration/admin, record-user tokens for adjusters."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

URL = os.getenv("SURREAL_URL", "http://localhost:8001")
NS = os.getenv("SURREAL_NS", "harbor")
DB = os.getenv("SURREAL_DB", "main")
ROOT = (os.getenv("SURREAL_USER", "root"), os.getenv("SURREAL_PASS", "root"))

# Demo adjusters created by the migration; the UI lets visitors act as either one.
PERSONAS = {
    "north": ("asha.north@harbor.example", "harbor-demo"),
    "south": ("ben.south@harbor.example", "harbor-demo"),
}

_http = httpx.Client(base_url=URL, timeout=60)
_tokens: dict[str, tuple[str, float]] = {}


class QueryError(RuntimeError):
    pass


def query(sql: str, vars: dict[str, Any] | None = None, *, as_: str | None = None) -> list[Any]:
    """Run SurrealQL; return each statement's result. `as_` = persona name, None = root."""
    headers = {"Accept": "application/json", "Surreal-NS": NS, "Surreal-DB": DB}
    auth = None
    if as_ is None:
        auth = ROOT
    else:
        headers["Authorization"] = f"Bearer {_token(as_)}"
    r = _http.post("/rpc", json={"id": 1, "method": "query", "params": [sql, vars or {}]},
                   headers=headers, auth=auth)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise QueryError(body["error"].get("message", str(body["error"])))
    out = []
    for i, s in enumerate(body["result"]):
        if s["status"] != "OK":
            raise QueryError(f"statement {i}: {s['result']}")
        out.append(s["result"])
    return out


def _token(persona: str) -> str:
    cached = _tokens.get(persona)
    if cached and cached[1] > time.time():
        return cached[0]
    email, password = PERSONAS[persona]
    r = _http.post("/signin", json={"ns": NS, "db": DB, "ac": "adjuster", "email": email, "pass": password},
                   headers={"Accept": "application/json"})
    r.raise_for_status()
    token = r.json()["token"]
    _tokens[persona] = (token, time.time() + 50 * 60)  # token lives 1h
    return token


def ready() -> bool:
    try:
        return _http.get("/health").status_code == 200
    except httpx.HTTPError:
        return False
