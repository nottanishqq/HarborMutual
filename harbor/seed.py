"""Build Harbor Mutual's legacy estate: Postgres (core records) + MongoDB (Cosmos stand-in).

Synthetic, seeded, so every run produces the same data. Eight fraud rings are planted:
one "witness" and one repair shop that keep turning up on unrelated, high-value claims.
In the last two rings the witness is also a customer (same name and phone): a second signal.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

import psycopg
from pymongo import MongoClient

PG_DSN = os.getenv("PG_DSN", "postgresql://harbor:harbor@localhost:5433/harbor")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27018")

FIRST = ("Aarav Maya Liam Zara Noah Isla Kabir Ava Omar Leah Ravi Chloe Ethan Priya Lucas Mei Sam Nora Arjun Ella"
         " Dev Freya Hassan Ruby Jack Anika Leo Sophie Yusuf Grace Rohan Amelia Finn Sana Oscar Tara").split()
LAST = ("Shah Patel Smith Jones Khan Brown Singh Taylor Wilson Clarke Evans Gupta Walker Reid Hughes Rao"
        " Ahmed Wright Green Mehta Hall Iyer Scott Bose Turner Ali Cooper Nair").split()
SHOPS = ["Quickfix Autos", "Northside Panel Beaters", "Southgate Motors", "Precision Body Works", "City Smash Repairs",
         "Harbour Auto Care", "Elm Park Garage", "Motorway Body Shop"]
CLINICS = ["Riverside Physio", "Harbour Medical Centre", "Elm Street Clinic", "Northgate Spine Clinic"]

CAR = [
    "Rear-ended at the {place} traffic lights while stationary. {damage}. Car taken to {shop}.",
    "Minor fender bender in the {place} car park, other driver reversed into my door. {damage}.",
    "Collided with a deer on the {place} road at night. {damage}; airbags deployed.",
    "Vehicle broken into outside {place}; window smashed and laptop stolen.",
    "Hailstorm near {place} left dents across the roof and bonnet. {damage}.",
    "Skidded on ice near {place} and hit a lamp post. {damage}. Whiplash reported.",
    "Hit by an uninsured driver at the {place} roundabout. {damage}. Car taken to {shop}.",
    "Side-swiped by a lorry merging on the {place} bypass. {damage}. Car taken to {shop}.",
    "Pothole on {place} burst the front tyre and bent the wheel rim.",
    "Car keyed along both sides while parked overnight on {place}.",
    "Stolen from the driveway overnight and later found burnt out near {place}.",
    "Flash flood on {place} got into the engine; car will not start.",
    "Cyclist rode into my parked car on {place}. {damage}.",
    "Shunted from behind in queuing traffic on {place}. {damage}. Whiplash reported. Car taken to {shop}.",
    "Wing mirror clipped by a passing van on {place}. {damage}.",
]
HOME = [
    "Burst pipe under the kitchen sink flooded the ground floor. Flooring and cabinets ruined.",
    "Water leak from the upstairs bathroom came through the {room} ceiling.",
    "Storm blew tiles off the roof; rain got into the {room}.",
    "Kitchen fire started by an unattended pan. Smoke damage throughout the {room}.",
    "Burglary while on holiday: TV, jewellery and laptop taken from the {room}.",
    "Subsidence cracks appeared in the {room} wall after a dry summer.",
    "Tree fell on the garage during high winds, crushing the roof.",
    "Washing machine hose split and soaked the {room} carpet.",
    "Frozen pipe in the loft cracked over winter; water came through the {room} ceiling.",
    "Lightning strike during a storm blew the boiler and the fuse board.",
    "Electrical fault in the {room} caused a small fire; wiring needs replacing.",
    "River flooding reached the ground floor; {room} and kitchen under water.",
    "Shed broken into, bikes and power tools stolen.",
    "Red wine spilt across the {room} sofa and rug.",
    "Dropped a tin of paint on the new {room} carpet.",
    "Blocked drain backed up and sewage came into the {room}.",
]
PLACES = ["High Street", "Market Square", "Station Road", "Riverside", "Elm Park", "Harbour Way",
          "Mill Lane", "Church Road", "Kingsway", "Dock Street"]
DAMAGE = ["Bumper and boot crushed", "Driver door dented", "Headlight and wing damaged",
          "Windscreen cracked", "Front end written off"]
# One extra detail per claim, so templated descriptions don't read identically.
EXTRAS = ["", "Happened around {hour}:00.", "Police reference {ref} given.", "Photos sent the same day.",
          "Customer away at the time.", "Second claim this year.", "Neighbour saw it happen.",
          "Reported {days} days later."]
ROOMS = ["living room", "bedroom", "hallway", "dining room", "study"]
NOTES = [
    "Customer called to chase progress on the claim.",
    "Requested photos of the damage and repair estimate.",
    "Estimate received from {shop}; looks higher than usual for this damage.",
    "Customer sent receipts for the stolen items.",
    "Loss adjuster visit booked for next week.",
    "Third party insurer confirmed liability accepted.",
    "Customer unhappy with delay, considering complaint.",
    "Medical report received from {clinic} for whiplash.",
    "Witness statement received, matches customer account closely.",
    "Customer asked whether a courtesy car is covered.",
    "Engineer's report says damage is older than the claimed date.",
    "Payment details confirmed with the customer by phone.",
    "Third party not responding to letters.",
]


def phone(rng: random.Random) -> str:
    return f"07{rng.randint(100, 999)} {rng.randint(100000, 999999)}"


def generate(seed: int = 7) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    name = lambda: f"{rng.choice(FIRST)} {rng.choice(LAST)}"  # noqa: E731

    adjusters = [
        {"id": 1, "name": "Asha Rao", "email": "asha.north@harbor.example", "region": "North"},
        {"id": 2, "name": "Ben Clarke", "email": "ben.south@harbor.example", "region": "South"},
        {"id": 3, "name": "Nora Evans", "email": "nora.north@harbor.example", "region": "North"},
        {"id": 4, "name": "Omar Khan", "email": "omar.south@harbor.example", "region": "South"},
    ]
    customers = []
    for i in range(1, 481):
        n = name()
        customers.append({"id": i, "name": n, "email": f"{n.lower().replace(' ', '.')}{i}@mail.example",
                          "phone": phone(rng), "region": rng.choice(["North", "South"])})
    policies = []
    for i in range(1, 601):
        c = customers[(i - 1) % len(customers)]
        policies.append({"id": i, "customer_id": c["id"], "kind": rng.choice(["home", "car"]),
                         "start_date": start - timedelta(days=rng.randint(30, 900)),
                         "premium": round(rng.uniform(250, 1400), 2)})

    parties = [{"id": i + 1, "name": s, "phone": phone(rng), "kind": "repair_shop"} for i, s in enumerate(SHOPS)]
    parties += [{"id": len(parties) + i + 1, "name": c, "phone": phone(rng), "kind": "clinic"}
                for i, c in enumerate(CLINICS)]

    def new_person() -> dict:
        p = {"id": len(parties) + 1, "name": name(), "phone": phone(rng), "kind": "person"}
        parties.append(p)
        return p

    claims, links, payments, notes = [], [], [], []
    by_cust = {c["id"]: c for c in customers}
    for i in range(1, 1351):
        p = rng.choice(policies)
        region = by_cust[p["customer_id"]]["region"]
        shop = rng.choice(SHOPS)
        tpl = rng.choice(CAR if p["kind"] == "car" else HOME)
        desc = tpl.format(place=rng.choice(PLACES), damage=rng.choice(DAMAGE), shop=shop, room=rng.choice(ROOMS))
        desc = f"{desc} {rng.choice(EXTRAS).format(hour=rng.randint(0, 23), ref=rng.randint(10000, 99999), days=rng.randint(2, 30))}".strip()
        filed = start + timedelta(days=rng.randint(0, 600), hours=rng.randint(0, 23))
        status = rng.choices(["open", "approved", "rejected"], [3, 5, 1])[0]
        claims.append({"id": i, "number": f"HM-{24000 + i}", "policy_id": p["id"],
                       "adjuster_id": rng.choice([a["id"] for a in adjusters if a["region"] == region]),
                       "region": region, "status": status, "amount": round(rng.uniform(300, 9000), 2),
                       "filed_at": filed, "description": desc})
        if p["kind"] == "car" and "taken to" in desc:
            links.append({"claim_id": i, "party_id": SHOPS.index(shop) + 1, "role": "repairer"})
        if rng.random() < 0.4:
            links.append({"claim_id": i, "party_id": new_person()["id"], "role": "witness"})
        if "Whiplash" in desc:
            links.append({"claim_id": i, "party_id": len(SHOPS) + rng.randint(1, len(CLINICS)), "role": "treating_clinic"})
        if status == "approved":
            payments.append({"claim_id": i, "amount": claims[-1]["amount"], "paid_at": filed + timedelta(days=rng.randint(5, 40))})
        for k in range(rng.randint(1, 3)):
            # Stable _id, so re-seeding and migrating again overwrites notes instead of duplicating them.
            notes.append({"_id": f"HM-{24000 + i}-{k}", "claim_number": f"HM-{24000 + i}", "channel": rng.choice(["email", "phone", "letter"]),
                          "author": rng.choice(["customer", "adjuster", "third party"]),
                          "body": rng.choice(NOTES).format(shop=shop, clinic=rng.choice(CLINICS)),
                          "sent_at": filed + timedelta(days=k * 3 + 1)})

    # Fraud rings: the same witness and repair shop on 4-6 big, recent car claims across customers.
    kind = {p["id"]: p["kind"] for p in policies}
    ring_claims = [c for c in claims if kind[c["policy_id"]] == "car"]
    rng.shuffle(ring_claims)
    for ring in range(8):
        witness = new_person()
        if ring >= 6:  # the witness is secretly one of our own customers
            witness.update(name=customers[ring]["name"], phone=customers[ring]["phone"])
        shop_id = ring + 1
        for c in ring_claims[ring * 6: ring * 6 + rng.randint(4, 6)]:
            c["amount"] = round(rng.uniform(7000, 14000), 2)
            c["status"] = "open"
            payments[:] = [p for p in payments if p["claim_id"] != c["id"]]
            links[:] = [l for l in links if l["claim_id"] != c["id"]]
            links.append({"claim_id": c["id"], "party_id": witness["id"], "role": "witness"})
            links.append({"claim_id": c["id"], "party_id": shop_id, "role": "repairer"})

    policy_docs = [{"policy_id": p["id"], "excess": rng.choice([100, 250, 500]),
                    "cover": ["accidental damage", "theft"] if p["kind"] == "home" else ["third party", "windscreen"],
                    "endorsements": rng.sample(["legal cover", "courtesy car", "home emergency"], rng.randint(0, 2))}
                   for p in policies]
    return {"adjusters": adjusters, "customers": customers, "policies": policies, "parties": parties,
            "claims": claims, "claim_parties": links, "payments": payments,
            "correspondence": notes, "policy_docs": policy_docs}


PG_DDL = """
DROP TABLE IF EXISTS payment, claim_party, claim, party, policy, customer, adjuster;
CREATE TABLE adjuster (id int PRIMARY KEY, name text, email text UNIQUE, region text);
CREATE TABLE customer (id int PRIMARY KEY, name text, email text, phone text, region text);
CREATE TABLE policy (id int PRIMARY KEY, customer_id int REFERENCES customer, kind text,
                     start_date timestamptz, premium numeric(10,2));
CREATE TABLE party (id int PRIMARY KEY, name text, phone text, kind text);
CREATE TABLE claim (id int PRIMARY KEY, number text UNIQUE, policy_id int REFERENCES policy,
                    adjuster_id int REFERENCES adjuster, region text, status text,
                    amount numeric(10,2), filed_at timestamptz, description text);
CREATE TABLE claim_party (claim_id int REFERENCES claim, party_id int REFERENCES party, role text,
                          PRIMARY KEY (claim_id, party_id));
CREATE TABLE payment (id serial PRIMARY KEY, claim_id int REFERENCES claim, amount numeric(10,2), paid_at timestamptz);
"""


def load(data: dict[str, list[dict]]) -> None:
    with psycopg.connect(PG_DSN) as pg, pg.cursor() as cur:
        cur.execute(PG_DDL)
        for table, rows in [("adjuster", data["adjusters"]), ("customer", data["customers"]),
                            ("policy", data["policies"]), ("party", data["parties"]),
                            ("claim", data["claims"]), ("claim_party", data["claim_parties"]),
                            ("payment", data["payments"])]:
            cols = list(rows[0])
            cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                            [tuple(r[c] for c in cols) for r in rows])
    mongo = MongoClient(MONGO_URL)["harbor"]
    for coll in ("correspondence", "policy_docs"):
        mongo[coll].drop()
        mongo[coll].insert_many([dict(d) for d in data[coll]])


def main() -> None:
    data = generate()
    load(data)
    print({k: len(v) for k, v in data.items()})


if __name__ == "__main__":
    main()
