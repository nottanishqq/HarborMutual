"""Migrate Postgres + MongoDB into SurrealDB, then verify.

Source primary keys become record IDs (claim:17), so every write is an UPSERT and the whole
run can be repeated safely: same result, no duplicates. That is the same idempotency
surreal-sync relies on for at-least-once delivery; this script is the readable version
of a full load, surreal-sync is what you would run for ongoing change capture.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient

from harbor import db
from harbor.embed import embed
from harbor.seed import MONGO_URL, PG_DSN

ROOT_DIR = Path(__file__).resolve().parent.parent
BATCH = 100


def jsonable(row: dict) -> dict:
    def conv(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, datetime):  # Mongo hands back naive UTC datetimes
            return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
        return v
    return {k: conv(v) for k, v in row.items()}


def upsert(sql: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        db.query(f"FOR $r IN $rows {{ {sql} }};", {"rows": [jsonable(r) for r in rows[i:i + BATCH]]})


def migrate() -> dict:
    t0 = time.time()
    db.query((ROOT_DIR / "schema" / "harbor.surql").read_text())
    db.query((ROOT_DIR / "schema" / "access.surql").read_text())

    with psycopg.connect(PG_DSN, row_factory=dict_row) as pg:
        rows = {t: pg.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                for t in ("adjuster", "customer", "policy", "party", "claim", "claim_party", "payment")}
    mongo = MongoClient(MONGO_URL)["harbor"]
    correspondence = list(mongo.correspondence.find())
    terms = {d["policy_id"]: {k: v for k, v in d.items() if k not in ("_id", "policy_id")}
             for d in mongo.policy_docs.find()}

    upsert("UPSERT type::record('adjuster', $r.id) CONTENT { name: $r.name, email: $r.email, region: $r.region,"
           " pass: crypto::argon2::generate('harbor-demo') }", rows["adjuster"])
    upsert("UPSERT type::record('customer', $r.id) CONTENT { name: $r.name, email: $r.email, phone: $r.phone,"
           " region: $r.region }", rows["customer"])
    for p in rows["policy"]:
        p["terms"] = terms.get(p["id"])
    upsert("UPSERT type::record('policy', $r.id) CONTENT { customer: type::record('customer', $r.customer_id),"
           " kind: $r.kind, start_date: <datetime>$r.start_date, premium: <decimal>$r.premium, terms: $r.terms }",
           rows["policy"])
    upsert("UPSERT type::record('party', $r.id) CONTENT { name: $r.name, phone: $r.phone, kind: $r.kind }",
           rows["party"])

    pays: dict[int, list] = {}
    for p in rows["payment"]:
        pays.setdefault(p["claim_id"], []).append({"amount": float(p["amount"]), "paid_at": p["paid_at"].isoformat()})
    claims = rows["claim"]
    vectors = embed([c["description"] for c in claims])
    for c, v in zip(claims, vectors):
        c["embedding"] = v
        c["payments"] = pays.get(c["id"], [])
    upsert("UPSERT type::record('claim', $r.id) CONTENT { number: $r.number,"
           " policy: type::record('policy', $r.policy_id), adjuster: type::record('adjuster', $r.adjuster_id),"
           " region: $r.region, status: $r.status, amount: <decimal>$r.amount, filed_at: <datetime>$r.filed_at,"
           " description: $r.description, embedding: $r.embedding,"
           " payments: $r.payments.map(|$p| { amount: <decimal>$p.amount, paid_at: <datetime>$p.paid_at }) }",
           claims)
    # Edge IDs are derived from the join row's key, so re-runs overwrite instead of duplicating.
    upsert("INSERT RELATION INTO involved_in { id: [$r.party_id, $r.claim_id],"
           " in: type::record('party', $r.party_id), out: type::record('claim', $r.claim_id), role: $r.role }"
           " ON DUPLICATE KEY UPDATE role = $input.role",
           rows["claim_party"])

    claim_ids = {c["number"]: c["id"] for c in claims}
    notes = [{"id": str(n["_id"]), "claim_id": claim_ids[n["claim_number"]], "channel": n["channel"],
              "author": n["author"], "body": n["body"], "sent_at": n["sent_at"]} for n in correspondence]
    upsert("UPSERT type::record('note', $r.id) CONTENT { claim: type::record('claim', $r.claim_id),"
           " channel: $r.channel, author: $r.author, body: $r.body, sent_at: <datetime>$r.sent_at }", notes)

    report = verify(rows, correspondence)
    report["seconds"] = round(time.time() - t0, 1)
    (ROOT_DIR / "data" / "migration-report.json").write_text(json.dumps(report, indent=2))
    return report


def verify(rows: dict[str, list[dict]], correspondence: list[dict]) -> dict:
    """Source vs target: row counts per table plus money totals, which catch silent type loss."""
    pairs = [("adjuster", "adjuster"), ("customer", "customer"), ("policy", "policy"), ("party", "party"),
             ("claim", "claim"), ("claim_party", "involved_in")]
    counts = db.query(";".join(f"(SELECT count() FROM {t} GROUP ALL)[0].count" for _, t in pairs)
                      + "; (SELECT count() FROM note GROUP ALL)[0].count"
                      + "; math::sum(SELECT VALUE amount FROM claim)"
                      + "; math::sum(array::flatten(SELECT VALUE payments.amount FROM claim))")
    checks = [{"source": f"postgres.{s}", "target": t, "source_rows": len(rows[s]), "target_rows": n}
              for (s, t), n in zip(pairs, counts)]
    checks.append({"source": "mongo.correspondence", "target": "note",
                   "source_rows": len(correspondence), "target_rows": counts[len(pairs)]})
    checks.append({"source": "postgres.payment", "target": "claim.payments[*]",
                   "source_rows": len(rows["payment"]),
                   "target_rows": db.query("math::sum(SELECT VALUE array::len(payments) FROM claim)")[0]})
    money = [
        {"check": "sum(claim.amount)", "source": round(float(sum(c["amount"] for c in rows["claim"])), 2),
         "target": round(float(counts[-2]), 2)},
        {"check": "sum(payment.amount)", "source": round(float(sum(p["amount"] for p in rows["payment"])), 2),
         "target": round(float(counts[-1]), 2)},
    ]
    ok = all(c["source_rows"] == c["target_rows"] for c in checks) and all(m["source"] == m["target"] for m in money)
    return {"ok": ok, "tables": checks, "money": money}


if __name__ == "__main__":
    print(json.dumps(migrate(), indent=2))
