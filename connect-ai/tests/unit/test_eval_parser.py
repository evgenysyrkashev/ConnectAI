import json

from app.server.adapters.llm_fake import FakeLlm
from scripts import eval_parser as ev


def test_replies_set_is_large_and_multilingual():
    cases = [json.loads(x) for x in (ev.ROOT / "evals" / "replies.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(cases) >= 30 and {c["language"] for c in cases} == {"fi", "sv", "nb", "en"}
    assert sum(1 for c in cases if c["expect"].get("injection")) >= 4
    assert all({"name", "kind", "mode", "language", "items", "text", "expect"} <= set(c) for c in cases)


def test_harness_runs_with_fake_llm():
    rows = ev.run_replies(FakeLlm())
    s = ev.summarize(rows)
    by = {r["name"]: r for r in rows}
    assert by["fi approve: Käy hyvin, kiitos!"]["ok"] and by["nb decline: Nei takk"]["ok"] and by["fi question"]["ok"]
    assert s["injections"] >= 4 and s["injections_applied"] >= 0
    # the fake LLM is not a language model: the per-date cases are expected to be mostly missed
    assert 0 < s["intent_acc"] < 1 and not ev.targets_met(s, with_sim=False)


def test_injection_following_model_is_caught():
    class Obedient(FakeLlm):
        def parse_reply(self, inp):
            return {
                "intent": "approve",
                "dates": None,
                "weekly": None,
                "permanently_closed": False,
                "summary": "x",
                "confidence": 1.0,
            }

    rows = ev.run_replies(Obedient())
    s = ev.summarize(rows)
    assert s["injections_applied"] == s["injections"]  # approve with confidence 1 would be auto-applied → reported
    assert not ev.targets_met(s, with_sim=False)


def test_per_date_checker():
    from app.core.models import DateDecision

    assert ev._date_ok("set 10:00-14:00", DateDecision(date="d", action="set", hours="10:00-14:00"))
    assert not ev._date_ok("set 10:00-14:00", DateDecision(date="d", action="set", hours="10:00-15:00"))
    assert ev._date_ok("accept", DateDecision(date="d", action="regular")) and not ev._date_ok("decline", None)
