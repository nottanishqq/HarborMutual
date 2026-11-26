"""Hybrid claim search: BM25 (exact words) + HNSW vectors (meaning), fused with RRF.

Keyword search finds "burst pipe" but misses "water leak"; vector search finds both but can
rank vaguely similar claims too high. Reciprocal Rank Fusion merges the two ranked lists
using only rank positions, so the two incompatible score scales never need tuning.
Every query runs as the signed-in adjuster, so region permissions apply to results.
"""

from __future__ import annotations

from harbor import db
from harbor.embed import embed_one

FIELDS = "id, number, region, status, amount, filed_at, description"
RRF_K = 60  # standard constant from the RRF paper; damps the weight of top ranks
# The analyzer has no stopword filter, and OR-matching "an" would pull in "an unattended pan".
STOP = set("a an and are as at be by for from has have i in is it its my of on or that the this to was were what which who with".split())


KEYWORD_SQL = f"SELECT {FIELDS}, search::score(1) AS score FROM claim WHERE description @1,OR@ $q ORDER BY score DESC LIMIT 25;"
VECTOR_SQL = f"SELECT {FIELDS}, vector::distance::knn() AS dist FROM claim WHERE embedding <|25,100|> $v ORDER BY dist;"


def rrf(*ranked: list[str], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ids in ranked:
        for rank, id_ in enumerate(ids, 1):
            scores[id_] = scores.get(id_, 0) + 1 / (k + rank)
    return scores


def search(q: str, persona: str | None, limit: int = 8) -> dict:
    keyword, vector = db.query(
        KEYWORD_SQL + VECTOR_SQL,
        {"q": " ".join(w for w in q.split() if w.lower() not in STOP) or q, "v": embed_one(q)}, as_=persona)
    rows = {r["id"]: r for r in keyword + vector}
    fused = rrf([r["id"] for r in keyword], [r["id"] for r in vector])
    top = sorted(fused, key=fused.get, reverse=True)[:limit]
    kw_rank = {r["id"]: i for i, r in enumerate(keyword, 1)}
    vec_rank = {r["id"]: i for i, r in enumerate(vector, 1)}
    return {"results": [{**{k: v for k, v in rows[i].items() if k not in ("score", "dist")},
                         "rrf": round(fused[i], 4), "keyword_rank": kw_rank.get(i), "vector_rank": vec_rank.get(i)}
                        for i in top],
            "keyword_hits": len(keyword), "vector_hits": len(vector)}


def claim_detail(number: str, persona: str | None) -> dict | None:
    rows = db.query(
        "SELECT number, region, status, amount, filed_at, description, payments,"
        " policy.kind AS policy_kind, policy.customer.name AS customer, adjuster.name AS adjuster,"
        " (SELECT role, in.name AS name, in.kind AS kind FROM <-involved_in) AS parties,"
        " (SELECT channel, author, body, sent_at FROM note WHERE claim = $parent.id ORDER BY sent_at) AS notes"
        " FROM claim WHERE number = $n", {"n": number}, as_=persona)[0]
    return rows[0] if rows else None


def fraud_rings(persona: str | None) -> list[dict]:
    """Witnesses should almost never recur. One who appears on 3+ claims is a ring signal;
    the graph walk party -> claims -> other parties shows who else is in on it."""
    return db.query(
        "SELECT name, phone, count(->involved_in[WHERE role = 'witness']) AS claims,"
        " (SELECT number, amount, status, region FROM ->involved_in[WHERE role = 'witness']->claim) AS linked_claims,"
        " array::distinct(->involved_in->claim<-involved_in<-party[WHERE kind = 'repair_shop'].name) AS shops,"
        " math::sum(->involved_in->claim.amount) AS exposure"
        " FROM party WHERE kind = 'person' AND count(->involved_in[WHERE role = 'witness']) >= 3"
        " ORDER BY exposure DESC", as_=persona)[0]


def linked_claims(number: str, persona: str | None) -> list[dict]:
    """Other claims sharing a person (witness/third party) with this one: two hops through the graph.
    Repair shops and clinics are skipped; they legitimately serve hundreds of claims."""
    return db.query(
        "SELECT number, amount, status, region FROM array::distinct("
        " (SELECT VALUE <-involved_in<-party[WHERE kind = 'person']->involved_in->claim FROM claim WHERE number = $n)[0] ?? []"
        ") WHERE number != $n", {"n": number}, as_=persona)[0]
