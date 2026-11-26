"""Ready-to-try examples for every tab, plus fixed SurrealQL checks the UI can run.

Checks are a closed list: the API runs only these strings, never SurrealQL from the browser,
and always as the selected adjuster, so region permissions still apply to every result.
Each one is shown verbatim in the UI as a starting point for writing your own in Surrealist.
"""

from __future__ import annotations

from harbor import search

SEARCH = [
    {"q": "car hit an animal", "why": "Keyword matches the word 'hit'; only the vector side finds 'collided with a deer'."},
    {"q": "vandalism", "why": "No claim contains the word, so BM25 finds nothing. Vectors still find break-ins by meaning."},
    {"q": "car stolen and set on fire", "why": "BM25 grabs 'fire' (house fires); vectors find 'found burnt out'. Fusion keeps both."},
    {"q": "burst pipe", "why": "Exact phrase: both sides agree, so the same claims top both lists."},
    {"q": "roof damaged in bad weather", "why": "Both contribute with different orders: watch keyword # vs vector # on each hit."},
    {"q": "stolen laptop", "why": "Switch adjuster and run again: same query, only your region's claims come back."},
]

SEARCH_TIPS = [
    "Exact words (a part, a place, 'whiplash') favour the keyword side; BM25 ORs the words, minus stopwords.",
    "Describe what happened in plain words ('neighbour's tree fell on my car') to lean on the vector side.",
    "A hit with both a keyword # and a vector # was found by both: those rise to the top under RRF.",
    "Very common words drown the keyword side ('after', 'car'); drop them to see the difference.",
]

# Claim used in the two-hop check: a North ring claim, so North and head office both see results.
RING_CLAIM = "HM-24108"

CHECKS = {
    "rings": {
        "tab": "fraud", "title": "Witnesses on 3+ claims (this page's query)",
        "why": "A witness should almost never recur. Count each person's witness edges and keep 3+.",
        "sql": "SELECT name, phone, count(->involved_in[WHERE role = 'witness']) AS claims\n"
               "FROM party WHERE kind = 'person' AND count(->involved_in[WHERE role = 'witness']) >= 3\n"
               "ORDER BY claims DESC;"},
    "two_hop": {
        "tab": "fraud", "title": f"Claims two hops from {RING_CLAIM}",
        "why": "claim <- person -> other claims: everything sharing a witness or third party. Swap in any claim number.",
        "sql": "SELECT VALUE array::distinct(<-involved_in<-party[WHERE kind = 'person']->involved_in->claim.number)\n"
               f"FROM claim WHERE number = '{RING_CLAIM}';"},
    "witness_is_customer": {
        "tab": "fraud", "title": "Witnesses who are also customers",
        "why": "Same phone on a witness and a policyholder: someone vouching for claims while insured with us.",
        "sql": "LET $phones = SELECT VALUE phone FROM customer;\n"
               "SELECT name, phone, count(->involved_in) AS claims_witnessed\n"
               "FROM party WHERE kind = 'person' AND phone INSIDE $phones;"},
    "big_open_witnessed": {
        "tab": "fraud", "title": "Biggest open claims that have a witness",
        "why": "Ring claims are planted big and open. Repeated witness names in this list are the tell.",
        "sql": "SELECT number, amount, <-involved_in[WHERE role = 'witness']<-party.name AS witness\n"
               "FROM claim WHERE status = 'open' AND amount > 7000\n"
               "  AND count(<-involved_in[WHERE role = 'witness']) > 0\n"
               "ORDER BY amount DESC LIMIT 15;"},
    "shops": {
        "tab": "fraud", "title": "Repair shops by claim value",
        "why": "Edges are records too: group the repairer edges by the shop on the in side.",
        "sql": "SELECT in.name AS shop, count() AS claims, math::sum(out.amount) AS total\n"
               "FROM involved_in WHERE role = 'repairer'\n"
               "GROUP BY shop ORDER BY total DESC;"},
    "region_totals": {
        "tab": "migration", "title": "Claims by region and status",
        "why": "Spot-check the migrated money from a different angle than the report.",
        "sql": "SELECT region, status, count() AS claims, math::sum(amount) AS total\n"
               "FROM claim GROUP BY region, status;"},
    "orphans": {
        "tab": "migration", "title": "Claims with a broken policy link",
        "why": "Foreign keys became record links; a dangling one would resolve to NONE. Expect 0.",
        "sql": "SELECT count() AS broken FROM claim WHERE policy.customer IS NONE GROUP ALL;"},
    "notes_per_channel": {
        "tab": "migration", "title": "Mongo correspondence by channel",
        "why": "Documents from MongoDB are now typed records linked to their claim.",
        "sql": "SELECT channel, count() AS notes FROM note GROUP BY channel;"},
}

ASK = [
    "Which open claims look like part of a fraud ring, and why?",
    f"Summarise claim {RING_CLAIM} and who else it is connected to.",
    "Find claims about water coming through a ceiling.",
    "Which repair shop keeps appearing with the same witness?",
    "Show me claims from the South region.",  # as a North adjuster: the database refuses
]


def payload() -> dict:
    return {
        "search": {"try": SEARCH, "tips": SEARCH_TIPS, "sql": [search.KEYWORD_SQL, search.VECTOR_SQL]},
        "ask": ASK,
        "checks": [{"id": k, **v} for k, v in CHECKS.items()],
    }
