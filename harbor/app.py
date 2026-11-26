"""HTTP API + single-page UI. Read-only demo: no endpoint accepts raw SurrealQL (checks are a fixed list)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from harbor import agent, db, examples, search

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Harbor on SurrealDB")

Persona = Literal["north", "south", "office"]


def who(persona: Persona) -> str | None:
    return None if persona == "office" else persona  # head office = root, sees every region


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/search")
def api_search(q: str = Query(min_length=2, max_length=300), as_: Persona = Query("north", alias="as")):
    return search.search(q, who(as_))


@app.get("/api/claim/{number}")
def api_claim(number: str, as_: Persona = Query("north", alias="as")):
    detail = search.claim_detail(number, who(as_))
    if not detail:
        raise HTTPException(404, "not found, or outside your region")
    return {**detail, "linked": search.linked_claims(number, who(as_))}


@app.get("/api/fraud")
def api_fraud(as_: Persona = Query("north", alias="as")):
    return search.fraud_rings(who(as_))


@app.get("/api/examples")
def api_examples():
    return examples.payload()


@app.get("/api/check/{name}")
def api_check(name: str, as_: Persona = Query("north", alias="as")):
    check = examples.CHECKS.get(name)
    if not check:
        raise HTTPException(404, "unknown check")
    return db.query(check["sql"], as_=who(as_))[-1]


@app.get("/api/migration")
def api_migration():
    return json.loads((ROOT.parent / "data" / "migration-report.json").read_text())


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    as_: Literal["north", "south"] = Field("north", alias="as")


@app.post("/api/ask")
def api_ask(body: Ask):
    if not agent.API_KEY:
        raise HTTPException(503, "The agent needs LLM_API_KEY set on the server.")
    return agent.ask(body.question, body.as_)
