# Harbor Mutual on SurrealDB

A fictional insurer, Harbor Mutual, runs claims on **Postgres** and keeps correspondence and policy documents in **MongoDB** (standing in for Azure Cosmos DB). This project migrates both into one **SurrealDB v4** database and builds on top of it:

- **Hybrid search.** BM25 full text and HNSW vectors, fused with Reciprocal Rank Fusion.
- **Fraud-ring detection** as graph traversals.
- **Region-level permissions** enforced inside the database.
- **A claims agent** with tools and private long-term memory per adjuster.

**Live demo:** https://harbormutual.onrender.com (free tier: first visit after 15 idle minutes takes about a minute to wake)

## What it shows

| Area | How |
| --- | --- |
| Data modelling across documents, graph and vectors | [`schema/harbor.surql`](schema/harbor.surql). Record links for 1-to-many (claim → policy → customer); embedded arrays for child rows only read with their parent (payments); `RELATE` edges with a `role` for the many-to-many party ↔ claim; vectors on the claim itself. |
| Migration from Postgres + MongoDB | [`harbor/migrate.py`](harbor/migrate.py). Source primary keys become record IDs, so every write is an upsert and re-runs are safe (idempotent). Foreign keys become record links, the join table becomes graph edges, and Mongo documents become typed records. |
| Verification | After every run: row counts per table and money totals, source vs target. The result appears in the app's *Migration report* tab. |
| Search and retrieval | [`harbor/search.py`](harbor/search.py). `@1,OR@` BM25 plus `<\|k,ef\|>` HNSW KNN, fused with RRF in Python. Example: *"car hit an animal"*. Keyword search finds "hit a lamp post", vector search finds "collided with a deer", and the fused list has both. |
| Graph queries | A witness appearing on 3 or more claims is a ring signal. `party->involved_in->claim<-involved_in<-party` shows the shared repair shops. Three rings are planted in the synthetic data and found. |
| Security | `DEFINE ACCESS ... TYPE RECORD` with argon2 sign-in, plus table `PERMISSIONS` keyed on `$auth.region`. A North adjuster cannot read South claims through the UI, the API or the agent, because the database refuses. |
| Agentic AI | [`harbor/agent.py`](harbor/agent.py). An LLM tool loop. The model never writes SurrealQL: it calls four read-only tools, each run with the adjuster's own token. After each answer it stores a memory note (embedded, HNSW-indexed, private per adjuster by table permission) and recalls the closest notes next time. |
| Tests | [`tests/test_harbor.py`](tests/test_harbor.py): RRF maths, permissions enforced by the DB, rings found, and the agent tool loop plus memory isolation (with a fake LLM). |

## Architecture

```
 Postgres (claims, policies,    MongoDB / "Cosmos"
 customers, parties, payments)  (correspondence, policy_docs)
            \                     /
             harbor/migrate.py  ── upsert by source PK, embed descriptions (bge-small, local)
                     |
              SurrealDB v4  ── documents + record links + RELATE edges + BM25 + HNSW + record-user permissions
                     |
            FastAPI (harbor/app.py) ── search · claim detail · fraud rings · agent · migration report
                     |
            static/index.html (persona switcher: North / South adjuster / head office)
```

**Hosted version:** one container on Render. SurrealDB runs in memory and loads the migrated snapshot (`data/harbor.surql`) at boot, next to the app. Root credentials are random per boot and never leave the container. Visitors act as demo adjusters (record users).

## Run locally

Needs Docker and [uv](https://docs.astral.sh/uv/).

```sh
docker compose up -d                 # Postgres :5433, Mongo :27018, SurrealDB :8001
uv sync
uv run python -m harbor.seed         # build the legacy estate (seeded, repeatable)
uv run python -m harbor.migrate      # Postgres + Mongo -> SurrealDB, then verify
uv run python -m pytest -q
uv run python -m uvicorn harbor.app:app --port 7860   # http://localhost:7860
```

For the agent, set an OpenAI-compatible endpoint. The default is Google Gemini's free tier:

```sh
LLM_API_KEY=...                      # https://aistudio.google.com/apikey
LLM_MODEL=gemini-2.5-flash           # or e.g. LLM_BASE_URL=https://api.groq.com/openai/v1
```

To refresh the hosted snapshot after a migration: `sh scripts/export.sh`.

## Deploy (free)

Render free web service (512 MB RAM; this app uses about 400 MB), built from the `Dockerfile`.

1. Render → New → Web Service → connect this repo. Runtime: Docker. Instance: Free.
2. Environment: add `LLM_API_KEY`.
3. Every push to `master` redeploys. The service sleeps after 15 idle minutes, and agent memory resets on each wake (the database is in memory).

## Decisions

- **Own migrator, not surreal-sync.** This is a one-off full load whose every step needed to be readable and verifiable. For ongoing change capture from a live Postgres or Mongo, use [surreal-sync](https://github.com/surrealdb/surreal-sync). It uses the same idea: primary keys become record IDs, which makes at-least-once delivery safe.
- **Payments are embedded, parties are edges.** Payments are only ever read with their claim. Parties are shared across claims and carry a role, and the fraud queries traverse them.
- **RRF in the app, not in SurrealQL.** It is a few lines, it is easy to test, and the API can show each hit's keyword and vector rank.
- **Stopwords are removed before BM25.** The analyzer has no stopword filter. Without this, OR-matching "an" would pull in "an unattended pan".
- **Local embeddings (bge-small, 384-d).** No API key or cost, and the same model is used at migration and at query time.

## Known limits

- The data is synthetic: about 450 claims, 890 notes and 3 planted fraud rings.
- The agent has no rate limit beyond the LLM provider's free-tier quota.
- Memory notes are written on every answer. There is no summarisation or forgetting yet.
