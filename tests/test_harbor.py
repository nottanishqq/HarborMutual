"""Run with the local stack up and migrated (see README). `uv run pytest`"""

import json
from types import SimpleNamespace as NS

import pytest

from harbor import agent, db, search


def test_rrf_rewards_agreement():
    s = search.rrf(["a", "b", "c"], ["b", "a", "d"])
    assert max(s, key=s.get) in ("a", "b") and s["a"] == s["b"] > s["c"] > 0 and s["d"] == s["c"]


def test_region_permissions_are_enforced_by_the_database():
    north = search.search("car crash", "north", 20)["results"]
    assert north and all(r["region"] == "North" for r in north)
    south_claim = db.query("SELECT VALUE number FROM claim WHERE region = 'South' LIMIT 1")[0][0]
    assert search.claim_detail(south_claim, "north") is None
    assert search.claim_detail(south_claim, "south") is not None


def test_planted_fraud_rings_are_found():
    rings = search.fraud_rings(None)
    assert len(rings) == 8 and all(r["claims"] >= 4 for r in rings)


def test_agent_tool_loop_and_private_memory(monkeypatch):
    """Fake LLM: calls fraud_rings once, then answers. Checks the tool ran with the
    adjuster's token and the memory note is invisible to the other adjuster."""
    db.query("DELETE memory")
    replies = iter([
        NS(content=None, tool_calls=[NS(id="1", function=NS(name="fraud_rings", arguments="{}"))]),
        NS(content="Ring around witness X: HM-1, HM-2.", tool_calls=None),
    ])
    seen = []

    class FakeClient:
        def __init__(self, **_):
            self.chat = NS(completions=NS(create=self.create))

        def create(self, messages, **_):
            seen.append(messages[-1])
            msg = next(replies)
            msg.model_dump = lambda **__: {"role": "assistant", "content": msg.content}
            return NS(choices=[NS(message=msg)])

    monkeypatch.setattr(agent, "OpenAI", FakeClient)
    monkeypatch.setattr(agent, "API_KEY", "test")
    out = agent.ask("Any fraud rings?", "north")
    assert out["trace"] == [{"tool": "fraud_rings", "args": {}}]
    tool_result = json.loads(seen[1]["content"])
    assert all(c["region"] == "North" for r in tool_result for c in r["linked_claims"])
    assert db.query("SELECT VALUE text FROM memory", as_="north")[0]
    assert db.query("SELECT VALUE text FROM memory", as_="south")[0] == []
    db.query("DELETE memory")
