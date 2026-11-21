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
    calls, answers, users = [], [], []

    def fake(model, system, user, schema, effort):
        calls.append(model)
        users.append(user)
        return copy.deepcopy(answers.pop(0))

    monkeypatch.setattr(llm, "call", fake)
    return SimpleNamespace(calls=calls, answers=answers, users=users)


def ranked(n=4):
    cands = fixture("candidates.json")["candidates"]
    return [{**c, "score": 9 - i, "kind": "act" if i == 0 else "know", "reason": "r"} for i, c in enumerate(cands[:n])]


def verdicts(*vs, review="pass"):
    return {"items": [{"id": f"c{i:02d}", "verdict": v, "issues": [], "fixed": None} for i, v in enumerate(vs, 1)],
            "review": {"verdict": review, "issues": [], "fixed": None},
            "term_review": {"verdict": "pass", "issues": [], "fixed": None},
            "soc_review": {"verdict": "pass", "issues": [], "fixed": None},
            "extras": {"verdict": "pass", "issues": [], "fixed": None}}


# ---------- caps ----------

def test_overlong_headline_rejected():
    item = fixture("draft.json")["items"][0]
    item["headline"] = "word " * 13
    assert any("headline" in e for e in llm.check_item(item))


def test_summary_and_notes_checked_and_options_allow_8_words():
    item = fixture("draft.json")["items"][0]
    assert llm.check_item(item) == []
    item["question"]["options"][0] = "one two three four five six seven eight"
    assert llm.check_item(item) == []
    for bad in ("Too short to read.", "word " * 81):
        item["summary"] = bad
        assert any("summary" in e for e in llm.check_item(item))
    item = fixture("draft.json")["items"][0]
    item["attack_note"] = None  # attack_id is set
    assert any("attack_note" in e for e in llm.check_item(item))
    item["attack_id"], item["actor"] = None, "word " * 26
    assert any("actor" in e for e in llm.check_item(item))


def test_glossary_and_til_never_repeat(repo):
    ex = {k: fixture("draft.json")[k] for k in ("glossary", "til")}
    assert llm.check_extras(ex) == []
    errs = llm.check_extras(ex, known_terms=["Zero-Day"], recent_til=["patch gap"])
    assert any("zero-day" in e for e in errs) and any("Patch Gap" in e for e in errs)


def test_history_comes_from_state_else_frozen_history_json(repo):
    assert llm.history() == ([], [])
    llm.save("history.json", {"glossary": ["t%d" % i for i in range(60)], "til": list("abcdefghij")})
    terms, tils = llm.history()
    assert len(terms) == 50 and terms[-1] == "t59" and tils == list("defghij")
    llm.save("data/state.json", {"days": [], "glossary": ["MFA"], "til": []})
    assert llm.history() == (["MFA"], [])


def test_url_in_model_string_rejected():
    item = fixture("draft.json")["items"][0]
    item["you"] = "See https://evil.example for more"
    assert any("no links" in e for e in llm.check_item(item))
    item["you"] = "Visit www.evil.example now"
    assert llm.check_item(item)


def as_update(item):
    return {**item, "summary": "word " * 20, "new": "Broadcom has released fixed vCenter builds."}


def test_update_caps():
    item = fixture("draft.json")["items"][0]
    item["new"] = "Something new."
    assert any("'new' must be null" in e for e in llm.check_item(item))
    up = as_update(fixture("draft.json")["items"][0])
    assert llm.check_item(up, update=True) == []
    assert any("needs 'new'" in e for e in llm.check_item({**up, "new": "word " * 31}, update=True))
    assert any("needs 'new'" in e for e in llm.check_item({**up, "new": None}, update=True))
    assert any("reminder" in e for e in llm.check_item({**up, "summary": "word " * 41}, update=True))
    assert any("reminder" in e for e in llm.check_item({**up, "summary": "word " * 14}, update=True))


def test_item_words_counts_new():
    it = {"headline": "h", "summary": "s", "you": "y", "new": "one two three"}
    assert critique.item_words(it) == critique.item_words({**it, "new": None}) + 3


UPDATE = {"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21", "hint": "fixed builds"}
SECOND = {"feed": "Bleeping Computer", "tier": 2, "title": "Second source title", "summary": "SECOND-SOURCE-TEXT"}


def multi_source_shortlist():
    short = ranked()
    short[0]["sources"] = [SECOND]
    short[1]["update"] = UPDATE
    short[1]["previous"] = {"headline": "Old", "first": "2026-11-21", "told": [{"date": "2026-11-21", "type": "first", "text": "PREVIOUS-TOLD"}]}
    short[1]["names"] = ["VMware vCenter"]
    return short


def test_write_and_critique_see_every_source_and_the_update(repo, canned):
    llm.save("out/ranked.json", {"shortlist": multi_source_shortlist()})
    draft = fixture("draft.json")
    draft["items"][1] = as_update(draft["items"][1])
    canned.answers += [draft, verdicts("pass", "pass", "pass", "pass")]
    assert write.main([]) == 0
    assert critique.main(["--mode", "full", "--date", "2026-11-22"]) == 0
    assert len(canned.calls) == 2  # the update draft passed its caps: no retry
    for user in canned.users:
        assert "SECOND-SOURCE-TEXT" in user and "PREVIOUS-TOLD" in user and "2026-11-21-c09" in user


def test_update_copied_from_shortlist_not_model(repo, canned):
    llm.save("out/ranked.json", {"shortlist": multi_source_shortlist()})
    draft = fixture("draft.json")
    draft["items"][1] = as_update(draft["items"][1])
    llm.save("out/draft.json", draft)
    v = verdicts("pass", "fixed", "pass", "pass")
    v["items"][1]["fixed"] = {**draft["items"][1], "update": {"story": "x", "type": "poc", "since": "2020-01-01"}}
    canned.answers.append(v)
    assert critique.main(["--mode", "full", "--date", "2026-11-22"]) == 0
    items = {i["id"]: i for i in llm.load("out/digest.json")["items"]}
    assert items["c02"]["update"] == {"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21"}
    assert items["c02"]["new"] == draft["items"][1]["new"] and items["c02"]["names"] == ["VMware vCenter"]
    assert items["c01"]["update"] is None and items["c01"]["new"] is None


def test_write_retries_once_then_fails_on_missing_item(repo, canned):
    llm.save("out/ranked.json", {"shortlist": ranked()})
    bad = fixture("draft.json")
    bad["items"].pop()
    canned.answers += [bad, bad]
    assert write.main([]) == 1
    assert len(canned.calls) == 2


def test_write_leaves_a_cap_break_to_the_critic(repo, canned):
    llm.save("out/ranked.json", {"shortlist": ranked()})
    bad = fixture("draft.json")
    bad["items"][1]["question"]["options"][0] = "one two three four five six seven eight nine"
    canned.answers += [bad, bad, verdicts("pass", "pass", "pass", "pass")]
    assert write.main([]) == 0
    assert len(canned.calls) == 2
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    assert [i["id"] for i in llm.load("out/digest.json")["items"]] == ["c01", "c03", "c04"]  # c02 still broken: dropped


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


def test_triage_tops_up_to_3_on_a_quiet_day(repo, canned):
    scores = {"c01": 3, "c02": 7, "c03": 4, "c04": 5, "c05": 2, "c06": 1}
    canned.answers.append({"items": [{"id": i, "score": s, "kind": "know", "reason": "x"} for i, s in scores.items()]})
    assert triage.main([]) == 0
    assert [s["id"] for s in llm.load("out/ranked.json")["shortlist"]] == ["c02", "c04", "c03"]


def test_triage_empty_candidates_no_call(repo, canned):
    llm.save("out/candidates.json", {"candidates": []})
    assert triage.main([]) == 0
    assert llm.load("out/ranked.json") == {"shortlist": []}
    assert canned.calls == []


def cli(monkeypatch, answer):
    """Fake `claude -p`: answer(model, argv, stdin) -> the CLI's JSON result dict. Returns the calls seen."""
    seen = []

    def run(cmd, input, **kw):
        model = cmd[cmd.index("--model") + 1]
        seen.append(SimpleNamespace(model=model, cmd=cmd, stdin=input, cwd=kw["cwd"]))
        return SimpleNamespace(returncode=0, stdout=json.dumps(answer(model, cmd, input)), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", run)
    return seen


def result(out=None, stop="end_turn", is_error=False, text=None):
    return {"type": "result", "is_error": is_error, "stop_reason": stop, "structured_output": out,
            "result": text if text is not None else json.dumps(out),
            "usage": {"input_tokens": 3, "cache_creation_input_tokens": 7, "output_tokens": 5}}


def test_call_runs_cli_without_tools(repo, monkeypatch):
    seen = cli(monkeypatch, lambda m, c, i: result({"ok": 1}))
    llm.spent.clear()
    assert llm.call(llm.OPUS, "sys", "user text", {"type": "object"}, "high") == {"ok": 1}
    [c] = seen
    assert c.cmd[:2] == ["claude", "-p"] and c.stdin == "user text"
    assert c.cmd[c.cmd.index("--tools") + 1] == ""
    assert c.cmd[c.cmd.index("--system-prompt") + 1] == "sys"
    assert json.loads(c.cmd[c.cmd.index("--json-schema") + 1]) == {"type": "object"}
    assert c.cmd[c.cmd.index("--effort") + 1] == "high"
    assert c.cwd != str(repo)  # never in the repo, so its CLAUDE.md is not read
    assert llm.spent == [(llm.OPUS, 10, 5)]


def test_call_parses_result_text_without_structured_output(repo, monkeypatch):
    cli(monkeypatch, lambda m, c, i: result(None, text='{"a": 2}'))
    assert llm.call(llm.HAIKU, "s", "u", {}, "low") == {"a": 2}


def test_cli_error_raises(repo, monkeypatch):
    cli(monkeypatch, lambda m, c, i: result(None, is_error=True, text="Failed to authenticate"))
    with pytest.raises(RuntimeError, match="Failed to authenticate"):
        llm.call(llm.HAIKU, "s", "u", {}, "low")
    assert triage.main([]) == 1


def test_refused_triage_reruns_on_sonnet(repo, monkeypatch):
    ok = {"items": [{"id": f"c{i:02d}", "score": 7, "kind": "know", "reason": "x"} for i in range(1, 7)]}
    seen = cli(monkeypatch, lambda m, c, i: result(None, "refusal", text="") if m == llm.HAIKU else result(ok))
    assert triage.main([]) == 0
    assert [c.model for c in seen] == [llm.HAIKU, llm.SONNET]
    assert len(llm.load("out/ranked.json")["shortlist"]) == 5


def test_refused_opus_raises(repo, monkeypatch):
    cli(monkeypatch, lambda m, c, i: result(None, "refusal", text=""))
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
    first = fixture("draft.json")["items"][0]
    assert {k: d["items"][0][k] for k in ("summary", "attack_note", "actor")} == \
        {k: first[k] for k in ("summary", "attack_note", "actor")}
    assert d["action"]["item_id"] == "c01"
    assert [q["kind"] for q in d["questions"]] == ["story", "term", "soc"]
    assert d["questions"][0]["topic"] == "T1203" and d["questions"][2]["topic"] == "triage"
    assert d["also"] == []
    assert [g["term"] for g in d["glossary"]] == ["zero-day"]  # XDR is not used in the picked items
    assert d["til"]["concept"] == "Patch Gap"


def test_critique_dropped_extras_leave_glossary_and_til_empty(repo, canned):
    critique_setup(canned, "pass", "pass", "pass", "pass")
    canned.answers[0]["extras"] = {"verdict": "drop", "issues": ["wrong definition"], "fixed": None}
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["glossary"] == [] and d["til"] is None and len(d["items"]) == 4
    assert [q["kind"] for q in d["questions"]] == ["story", "soc"]  # no word list shown: no term question


def test_pick_takes_3_then_more_only_within_word_budget():
    def it(n):
        return {"headline": "h", "summary": "w " * n, "you": "y", "attack_note": None, "actor": None}
    assert len(critique.pick([it(40)] * 7, "full")) == 5   # 230 + 5 * 50 = 480
    assert len(critique.pick([it(100)] * 7, "full")) == 4  # 230 + 4 * 110 = 670; a 5th would be 780 > 700
    assert len(critique.pick([it(200)] * 7, "full")) == 3  # never fewer than 3 when 3 pass
    assert len(critique.pick([it(40)] * 7, "small")) == 1


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
    assert [(q["kind"], q["topic"]) for q in d["questions"]] == [("review", "ports")]


def test_critique_everything_dropped_none(repo, canned):
    critique_setup(canned, "drop", "drop", "drop", "drop", review="drop")
    assert critique.main(["--mode", "full", "--date", "2026-11-21"]) == 0
    d = llm.load("out/digest.json")
    assert d["mode"] == "none" and d["questions"] == []


def test_critique_fix_breaking_cap_is_drop(repo, canned):
    critique_setup(canned, "fixed", "pass", "pass", "pass")
    fixed = fixture("draft.json")["items"][0]
    fixed["headline"] = "word " * 13
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
