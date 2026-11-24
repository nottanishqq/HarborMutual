"""Claims assistant: an LLM tool loop over the same permission-scoped queries as the UI.

The model never writes SurrealQL; it can only call the four tools below, and each runs with
the adjuster's own token. So a prompt like "show me South claims" from a North adjuster
returns nothing: the database refuses, not the prompt.

Memory: after each answer, a one-line note is stored in `memory` (private per adjuster,
enforced by table permissions) and the closest notes are recalled into the next prompt.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from harbor import db, search
from harbor.embed import embed_one

# Any OpenAI-compatible endpoint. Default: Google Gemini's free tier.
BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("LLM_API_KEY")
MAX_STEPS = 6

TOOLS = [
    {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": list(props)}}}
    for name, desc, props in [
        ("search_claims", "Hybrid keyword+semantic search over claim descriptions.", {"query": {"type": "string"}}),
        ("get_claim", "Full claim: policy, customer, parties, payments, correspondence.", {"number": {"type": "string", "description": "e.g. HM-24008"}}),
        ("linked_claims", "Other claims sharing a witness or third party with this claim.", {"number": {"type": "string"}}),
        ("fraud_rings", "Witnesses who recur across 3+ claims, with linked claims and total exposure.", {}),
    ]
]

SYSTEM = """You are Harbor Mutual's claims assistant for adjuster {name} ({region} region).
Answer from tool results only and cite claim numbers. If a tool returns nothing, say you
cannot see it; never guess. Amounts are in GBP (£). Be brief.
Things you remember from earlier conversations with this adjuster:
{memories}"""


def run_tool(name: str, args: dict, persona: str):
    if name == "search_claims":
        return [{k: r[k] for k in ("number", "region", "status", "amount", "description")}
                for r in search.search(args["query"], persona, 6)["results"]]
    if name == "get_claim":
        return search.claim_detail(args["number"], persona) or "not found or not visible to you"
    if name == "linked_claims":
        return search.linked_claims(args["number"], persona)
    if name == "fraud_rings":
        return search.fraud_rings(persona)
    return f"unknown tool {name}"


def ask(question: str, persona: str) -> dict:
    if not API_KEY:
        raise RuntimeError("LLM_API_KEY is not set")
    me, memories = db.query(
        "SELECT name, region FROM ONLY $auth;"
        "SELECT VALUE text FROM memory WHERE embedding <|3,40|> $v;",
        {"v": embed_one(question)}, as_=persona)
    messages = [
        {"role": "system", "content": SYSTEM.format(name=me["name"], region=me["region"],
                                                    memories="\n".join(f"- {m}" for m in memories) or "- nothing yet")},
        {"role": "user", "content": question},
    ]
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    trace = []
    for _ in range(MAX_STEPS):
        msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS).choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            break
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = run_tool(call.function.name, args, persona)
            trace.append({"tool": call.function.name, "args": args})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
    answer = msg.content or "(no answer)"
    note = f"Asked: {question[:200]} | Answered: {answer[:300]}"
    db.query("CREATE memory SET text = $t, embedding = $v", {"t": note, "v": embed_one(note)}, as_=persona)
    return {"answer": answer, "trace": trace, "recalled": memories}
