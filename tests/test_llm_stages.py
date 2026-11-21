import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from brief import critique, llm, triage, weekly, write

FIX = Path(__file__).parent / "fixtures" / "llm"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("profile.md").write_text("i use: Windows, Chrome, Outlook\n", encoding="utf-8")
    llm.save("out/candidates.json", fixture("candidates.json"))
    return tmp_path


@pytest.fixture
def canned(monkeypatch):
    """Replace llm.call with a queue of canned JSON answers; record each call."""
    calls, answers = [], []

    def fake(model, system, user, schema, effort):
        calls.append(model)
        return copy.deepcopy(answers.pop(0))

    monkeypatch.setattr(llm, "call", fake)
    return SimpleNamespace(calls=calls, answers=answers)


def ranked(n=4):
    cands = fixture("candidates.json")["candidates"]
    return [{**c, "score": 9 - i, "kind": "act" if i == 0 else "know", "reason": "r"} for i, c in enumerate(cands[:n])]


def verdicts(*vs, review="pass"):
    return {"items": [{"id": f"c{i:02d}", "verdict": v, "issues": [], "fixed": None} for i, v in enumerate(vs, 1)],
            "review": {"verdict": review, "issues": [], "fixed": None}}


# ---------- caps ----------

def test_overlong_headline_rejected():
    item = fixture("draft.json")["items"][0]
    item["headline"] = "one two three four five six seven eight nine ten eleven"
    assert any("headline" in e for e in llm.check_item(item))


def test_url_in_model_string_rejected():
    item = fixture("draft.json")["items"][0]
    item["you"] = "See https://evil.example for more"
    assert any("no links" in e for e in llm.check_item(item))
    item["you"] = "Visit www.evil.example now"
    assert llm.check_item(item)


def test_write_retries_once_then_fails(repo, canned):
    llm.save("out/ranked.json", {"shortlist": ranked()})
    bad = fixture("draft.json")
    bad["items"][1]["question"]["options"] = ["a", "b"]
    canned.answers += [bad, bad]
    assert write.main([]) == 1
    assert len(canned.calls) == 2


def test_write_fixes_on_retry(repo, canned):
    llm.save("out/ranked.json", {"shortlist": ranked()})
    bad = fixture("draft.json")
    bad["items"][0]["headline"] = "word " * 11
    canned.answers += [bad, fixture("draft.json")]
    assert write.main([]) == 0
    assert [i["id"] for i in llm.load("out/draft.json")["items"]] == ["c01", "c02", "c03", "c04"]


# ---------- triage ----------

def test_triage_keeps_top5_score_6_plus(repo, canned):
    scores = {"c01": 9, "c02": 6, "c03": 5, "c04": 8, "c05": 7, "c06": 10}
    kinds = {"c06": "skip"}
    canned.answers.append({"items": [{"id": i, "score": s, "kind": kinds.get(i, "know"), "reason": "x"}
                                     for i, s in scores.items()]})
    assert triage.main([]) == 0
    short = llm.load("out/ranked.json")["shortlist"]
    assert [s["id"] for s in short] == ["c01", "c04", "c05", "c02"]
    assert short[0]["url"] == "https://example.com/c01"
    assert canned.calls == [llm.HAIKU]


def test_triage_empty_candidates_no_call(repo, canned):
    llm.save("out/candidates.json", {"candidates": []})
    assert triage.main([]) == 0
    assert llm.load("out/ranked.json") == {"shortlist": []}
    assert canned.calls == []


def test_refused_triage_reruns_on_sonnet(repo, monkeypatch):
    seen = []

    def resp(stop, text):
        return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    ok = json.dumps({"items": [{"id": f"c{i:02d}", "score": 7, "kind": "know", "reason": "x"} for i in range(1, 7)]})

    class Msgs:
        def create(self, **kw):
            seen.append(kw["model"])
            return resp("refusal", "") if kw["model"] == llm.HAIKU else resp("end_turn", ok)

    fake = SimpleNamespace(messages=Msgs(), beta=SimpleNamespace(messages=Msgs()))
    monkeypatch.setattr(llm, "client", lambda: fake)
    assert triage.main([]) == 0
    assert seen == [llm.HAIKU, llm.SONNET]
    assert len(llm.load("out/ranked.json")["shortlist"]) == 5


def test_refused_opus_raises(repo, monkeypatch):
    msgs = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        stop_reason="refusal", content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=0)))
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs)))
    with pytest.raises(llm.Refused):
        llm.call(llm.OPUS, "s", "u", {}, "medium")


# ---------- critique ----------

def critique_setup(canned, *vs, review="pass"):
    llm.save("out/ranked.json", {"shortlist": ranked()})
    llm.save("out/draft.json", fixture("draft.json"))
    canned.answers.append(verdicts(*vs, review=review))


def test_critique_url_copied_from_candidate(repo, canned):
    critique_setup(canned, "pass", "pass", "pass", "pass")
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    cands = {c["id"]: c for c in fixture("candidates.json")["candidates"]}
    for it in d["items"] + d["also"]:
        assert it["url"] == cands[it["id"]]["url"]
        assert it["feed"] == cands[it["id"]]["feed"]
    assert d["items"][0]["keys"] == cands["c01"]["keys"]


def test_critique_picks_3_in_rank_order(repo, canned):
    critique_setup(canned, "pass", "drop", "pass", "pass")
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["mode"] == "full"
    assert [i["id"] for i in d["items"]] == ["c01", "c03", "c04"]
    assert d["action"]["item_id"] == "c01"
    assert d["question"]["topic"] == "T1203"
    assert d["also"] == []


def test_critique_small_mode_picks_1(repo, canned):
    critique_setup(canned, "drop", "pass", "pass", "pass")
    assert critique.main(["--mode", "small", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["mode"] == "small"
    assert [i["id"] for i in d["items"]] == ["c02"]
    assert [a["id"] for a in d["also"]] == ["c03", "c04"]
    assert d["action"] is None


def test_critique_all_dropped_quiz_only(repo, canned):
    critique_setup(canned, "drop", "drop", "drop", "drop")
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["mode"] == "quiz_only" and d["items"] == []
    assert d["question"]["topic"] == "ports"


def test_critique_everything_dropped_none(repo, canned):
    critique_setup(canned, "drop", "drop", "drop", "drop", review="drop")
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["mode"] == "none" and d["question"] is None


def test_critique_fix_breaking_cap_is_drop(repo, canned):
    critique_setup(canned, "fixed", "pass", "pass", "pass")
    fixed = fixture("draft.json")["items"][0]
    fixed["headline"] = "word " * 12
    canned.answers[0]["items"][0]["fixed"] = fixed
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    assert [i["id"] for i in llm.load("out/digest.json")["items"]] == ["c02", "c03", "c04"]


# ---------- weekly ----------

def test_weekly_no_digests_no_call(repo, canned):
    assert weekly.main(["--date", "2026-11-22"]) == 0
    assert llm.load("out/weekly.json") == {"date": "2026-11-22", "pattern": None, "pick": None}
    assert canned.calls == []


def test_weekly_resolves_pick(repo, canned):
    llm.save("data/digests/2026-11-20.json", {"date": "2026-11-20", "items": [
        {"id": "c01", "kind": "act", "headline": "Chrome zero-day", "attack_id": "T1203",
         "url": "https://example.com/c01", "feed": "The Hacker News"}], "also": []})
    llm.save("data/digests/2026-11-10.json", {"date": "2026-11-10", "items": [], "also": []})  # outside the week
    canned.answers.append({"pattern": "Browsers were the way in.", "pick": {"date": "2026-11-20", "id": "c01", "why": "Shows exploit chains."}})
    assert weekly.main(["--date", "2026-11-22"]) == 0
    w = llm.load("out/weekly.json")
    assert w["pick"] == {"headline": "Chrome zero-day", "url": "https://example.com/c01",
                         "feed": "The Hacker News", "why": "Shows exploit chains."}
