import io
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from brief import deliver, state as st

FIX = Path(__file__).parent / "fixtures" / "deliver"
TOKEN = "123456:SECRET-TOKEN"


class FakeTelegram:
    """Stands in for urllib.request.urlopen. `responses` maps method -> result dict or HTTP error code."""

    def __init__(self, responses=None):
        self.calls, self.responses = [], responses or {}

    def __call__(self, req, timeout=None):
        method = req.full_url.rsplit("/", 1)[1]
        self.calls.append((method, json.loads(req.data)))
        res = self.responses.get(method, {"message_id": 4711})
        if isinstance(res, int):
            body = io.BytesIO(json.dumps({"ok": False, "description": "Bad Request: poll has already been closed"}).encode())
            raise urllib.error.HTTPError(req.full_url, res, "err", {}, body)
        return io.BytesIO(json.dumps({"ok": True, "result": res}).encode())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    (tmp_path / "out").mkdir()
    shutil.copy(FIX / "digest.json", "out/digest.json")
    shutil.copy(FIX / "weekly.json", "out/weekly.json")
    fake = FakeTelegram()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def digest():
    return json.loads((FIX / "digest.json").read_text(encoding="utf-8"))


def write_digest(d):
    Path("out/digest.json").write_text(json.dumps(d), encoding="utf-8")


def day(date, answered=True, correct=True, mode="full", poll=1, reasked=False):
    return {"date": date, "mode": mode, "sent_at": f"{date}T05:20:00Z", "keys": [], "titles": [],
            "poll_message_id": poll if mode not in ("weekly", "none") else None,
            "question": digest()["questions"][0], "answered": answered, "correct": correct, "reasked": reasked}


def new_day(date, answers, mode="full"):
    """A day in the 3-poll format. answers: list of (answered, correct) per poll."""
    return {"date": date, "mode": mode, "sent_at": f"{date}T05:20:00Z", "keys": [], "titles": [],
            "answered": None if any(a is None for a, _ in answers) else any(a for a, _ in answers),
            "polls": [{"message_id": 100 + i, "question": q, "answered": a, "correct": c, "reasked": False}
                      for i, ((a, c), q) in enumerate(zip(answers, digest()["questions"]))]}


def test_send_delivers_message_then_silent_quiz_and_records_state(repo):
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    assert [m for m, _ in repo.calls] == ["sendMessage", "sendMessage", "sendPoll", "sendPoll", "sendPoll"]
    stories, extras, poll = (c[1] for c in repo.calls[:3])
    assert [c[1]["question"] for c in repo.calls[3:]] == ["What is a hash?", digest()["questions"][2]["text"]]
    assert stories["parse_mode"] == "HTML" and stories["link_preview_options"] == {"is_disabled": True}
    first = stories["text"].split("\n\n")[0]
    assert first.startswith("🔴 <b>Chrome zero-day is being exploited</b>\nAttackers are already exploiting")
    assert "<i>Why it matters to you:</i> You run Chrome" in first and ">Source</a>: The Hacker News</i>" in first
    assert "🎯 <a href=\"https://attack.mitre.org/techniques/T1187/\">T1187</a> Forced Authentication:" in stories["text"]
    assert "👤 UNC5221: China-linked" in stories["text"]
    assert extras["text"].startswith("💡 <b>Today I learned: Forced Authentication</b>")
    assert "📖 <b>Words of the day</b>\n• <b>hash</b>:" in extras["text"]
    assert "▶ Do now (1 min): ⋮ → Help → About Google Chrome → Relaunch\n<i>For: Chrome zero-day" in extras["text"]
    assert extras["text"].endswith("Done. 3 quick questions below ↓")
    assert poll["disable_notification"] is True and poll["correct_option_ids"] == [1]
    s = st.load()
    assert s["glossary"] == ["hash", "root"] and s["til"] == ["Forced Authentication"]
    d = s["days"][-1]
    assert [p["message_id"] for p in d["polls"]] == [4711] * 3 and d["answered"] is None
    assert [p["question"]["kind"] for p in d["polls"]] == ["story", "term", "soc"]
    assert "cve-2026-125350" in d["keys"] and d["titles"][0] == "Chrome zero-day is being exploited"
    assert json.loads(Path("data/digests/2026-11-21.json").read_text(encoding="utf-8")) == digest()


def test_word_cap_blocks_the_send(repo):
    d = digest()
    d["items"][0]["you"] = "word " * 800
    write_digest(d)
    assert deliver.main(["send", "--date", "2026-11-21"]) == 1
    assert repo.calls == [] and not Path("data/state.json").exists()


def test_model_text_is_escaped(repo):
    d = digest()
    d["items"][0]["headline"] = "<script> & friends"
    text = "\n\n".join(deliver.render(d, st.load()))
    assert "&lt;script&gt; &amp; friends" in text and "<script>" not in text
    assert 'href="https://www.securityweek.com/outlook-hash-leak/?a=1&amp;b=2"' in text


def test_second_send_for_same_date_is_refused_unless_forced(repo):
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    assert deliver.main(["send", "--date", "2026-11-21"]) == 1
    assert len(repo.calls) == 5
    assert deliver.main(["send", "--date", "2026-11-21", "--force"]) == 0
    assert len(st.load()["days"]) == 1


def test_long_message_splits_at_blank_lines_under_4096():
    blocks = ["<b>x</b>" + "y" * 1500 for _ in range(5)]
    parts = deliver.chunks("\n\n".join(blocks))
    assert len(parts) == 3 and all(len(p) <= 4096 for p in parts)
    assert "\n\n".join(parts) == "\n\n".join(blocks)


def test_glossary_and_til_history_is_capped(repo):
    st.save({"version": 1, "days": [], "glossary": [f"t{i}" for i in range(50)], "til": list("abcdefg")})
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    s = st.load()
    assert len(s["glossary"]) == 50 and s["glossary"][-2:] == ["hash", "root"] and s["glossary"][0] == "t2"
    assert s["til"] == list("bcdefg") + ["Forced Authentication"]


def test_dots_and_streak_across_answered_unanswered_and_no_quiz():
    s = {"days": [
        day("2026-11-14", answered=True),
        day("2026-11-15", answered=False),       # ⬜ breaks the streak
        day("2026-11-16", answered=True),
        day("2026-11-17", mode="none"),          # ➖ does not break it
        # 2026-11-18 missing                     # ➖
        day("2026-11-19", answered=True),
        day("2026-11-20", mode="weekly"),        # ➖
    ]}
    assert st.dots(s, "2026-11-21") == "✅⬜✅➖➖✅➖"
    assert st.streak(s) == 2
    s["days"].append(day("2026-11-21", answered=None))  # sent, not yet synced: does not break
    assert st.streak(s) == 2


def test_small_mode_after_two_unanswered_quiz_days():
    s = {"days": [day("2026-11-17", answered=True), day("2026-11-18", answered=False),
                  day("2026-11-19", mode="none"), day("2026-11-20", answered=False)]}
    assert st.next_mode(s, "2026-11-21") == "small"
    s["days"][-1]["answered"] = True
    assert st.next_mode(s, "2026-11-21") == "full"
    assert st.next_mode(s, "2026-11-22") == "weekly"           # Sunday with briefs in the week
    assert st.next_mode({"days": []}, "2026-11-22") == "full"  # Sunday with nothing sent


def test_sync_turns_voter_counts_into_answered_and_correct(repo):
    st.save({"version": 1, "days": [day("2026-11-20", answered=None, correct=None, poll=99)]})
    repo.responses["stopPoll"] = {"total_voter_count": 1,
                                  "options": [{"voter_count": 1}, {"voter_count": 0}, {"voter_count": 0}]}
    assert deliver.main(["sync"]) == 0
    assert repo.calls == [("stopPoll", {"chat_id": "42", "message_id": 99})]
    d = st.load()["days"][-1]
    assert d["answered"] is True and d["polls"][0]["correct"] is False  # tapped option 0, correct is 1


def test_sync_closes_every_poll_and_a_day_counts_if_one_was_answered(repo):
    st.save({"version": 1, "days": [new_day("2026-11-20", [(None, None)] * 3)]})
    answers = iter([0, 1, 0])  # voters per poll: only the second was answered
    def stop(req, timeout=None):
        n = next(answers)
        repo.calls.append(("stopPoll", json.loads(req.data)))
        opts = [{"voter_count": 0}, {"voter_count": n}, {"voter_count": 0}]  # every vote goes to option 1
        return io.BytesIO(json.dumps({"ok": True, "result": {"total_voter_count": n, "options": opts}}).encode())
    urllib.request.urlopen = stop
    assert deliver.main(["sync"]) == 0
    assert [c[1]["message_id"] for c in repo.calls] == [100, 101, 102]
    d = st.load()["days"][-1]
    assert [p["answered"] for p in d["polls"]] == [False, True, False] and d["answered"] is True
    assert st.score(d) == (0, 3)  # the term poll's right option is 0
    assert st.streak(st.load()) == 1


def test_footer_shows_the_last_quiz_score(repo):
    st.save({"version": 1, "days": [new_day("2026-11-20", [(True, True), (True, False), (False, False)])]})
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    assert "Done. Last quiz 1/3 · Last 7 days" in repo.calls[1][1]["text"]


def test_sync_closed_poll_counts_as_unanswered(repo):
    st.save({"version": 1, "days": [day("2026-11-20", answered=None, correct=None)]})
    repo.responses["stopPoll"] = 400
    assert deliver.main(["sync"]) == 0
    assert st.load()["days"][-1]["answered"] is False


def test_dry_run_does_no_network_and_no_writes(repo, capsys):
    assert deliver.main(["send", "--dry-run", "--date", "2026-11-21"]) == 0
    st.save({"version": 1, "days": [day("2026-11-20", answered=None, correct=None)]})
    before = Path("data/state.json").read_text(encoding="utf-8")
    assert deliver.main(["sync", "--dry-run"]) == 0
    assert deliver.main(["send", "--dry-run", "--weekly", "--date", "2026-11-22"]) == 0
    assert repo.calls == []
    assert Path("data/state.json").read_text(encoding="utf-8") == before
    assert not Path("data/digests").exists()
    assert '"correct_option_ids"' in capsys.readouterr().out


def test_quiz_only_and_none_modes(repo):
    d = digest()
    d.update(mode="quiz_only", items=[], action=None)
    write_digest(d)
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    assert repo.calls[0][1]["text"] == "Nothing worth your minute today. 3 questions:"
    d.update(date="2026-11-23", mode="none", questions=[])
    write_digest(d)
    repo.calls.clear()
    assert deliver.main(["send", "--date", "2026-11-23"]) == 0
    assert repo.calls == [] and st.load()["days"][-1]["mode"] == "none"


def test_weekly_counts_from_state_and_reasks_missed_questions(repo):
    st.save({"version": 1, "days": [
        day("2026-11-16", answered=False),
        day("2026-11-17", answered=True, correct=False),
        day("2026-11-18", answered=True, correct=True),
        day("2026-11-19", answered=False),
        day("2026-11-21", answered=True, correct=True),
    ]})
    assert deliver.main(["send", "--weekly", "--date", "2026-11-22"]) == 0
    text = repo.calls[0][1]["text"]
    assert text.startswith("📅 Your week: read 3 of 5 · 2 of 3 right · streak 1")
    assert [m for m, _ in repo.calls] == ["sendMessage", "sendPoll", "sendPoll", "sendPoll"]
    assert "3 questions you missed or got wrong come next" in text
    s = st.load()
    assert [st.polls(d)[0]["reasked"] for d in s["days"][:4]] == [True, True, False, True]  # missed or wrong; the 18th was right
    assert s["days"][-1]["mode"] == "weekly"


def test_errors_never_print_the_token(repo, capsys):
    repo.responses["sendMessage"] = 401
    assert deliver.main(["send", "--date", "2026-11-21"]) == 1
    out = capsys.readouterr().out
    assert "sendMessage failed" in out and TOKEN not in out and "42" not in out
    assert not Path("data/state.json").exists()


def test_update_item_renders_whats_new_and_reminder():
    d = digest()
    plain = deliver.render(d, {"days": []})
    d["items"][0] |= {"update": {"story": "2026-11-20-c01", "type": "patch", "since": "2026-11-21"},
                      "new": "Google shipped the fix.", "summary": "Chrome had a zero-day under attack."}
    stories = deliver.render(d, {"days": []})[0]
    first, *rest = stories.split("\n\n")
    assert first.startswith("🔄 <b>Update: Chrome zero-day is being exploited</b>")
    assert "<i>What's new since 21 Nov:</i> Google shipped the fix." in first
    assert "<i>Reminder:</i> Chrome had a zero-day under attack." in first
    assert "🔴" not in first and "Why it matters to you:" in first
    assert rest == plain[0].split("\n\n")[1:]  # other items unchanged


# ---------- story memory ----------

def item(i, headline="Old story", **kw):
    return {"id": i, "headline": headline, "summary": f"SUMMARY-{i}", "keys": [f"u:x.test/{i}"], **kw}


def test_sent_item_creates_a_story_record(repo):
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    [r, *_] = st.load()["stories"]
    assert r["id"] == "2026-11-21-c01" and r["first"] == r["last"] == "2026-11-21"
    assert r["told"] == [{"date": "2026-11-21", "type": "first", "text": digest()["items"][0]["summary"]}]
    assert "cve-2026-125350" in r["keys"]


def test_update_appends_to_told_and_moves_last():
    s = {"days": []}
    st.remember_stories(s, {"date": "2026-11-21", "items": [item("c09", names=["Armory Castle"])]})
    up = item("c02", update={"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21"},
              new="Fixed builds are out.", names=["VMware vCenter"])
    st.remember_stories(s, {"date": "2026-11-24", "items": [up]})
    [r] = s["stories"]
    assert r["last"] == "2026-11-24" and r["first"] == "2026-11-21"
    assert r["told"][-1] == {"date": "2026-11-24", "type": "patch", "text": "Fixed builds are out."}
    assert r["names"] == ["Armory Castle", "VMware vCenter"] and r["keys"] == ["u:x.test/c09", "u:x.test/c02"]


def test_story_15_days_old_is_removed():
    s = {"days": []}
    st.remember_stories(s, {"date": "2026-11-01", "items": [item("c01")]})
    st.remember_stories(s, {"date": "2026-11-15", "items": [item("c02")]})
    assert [r["id"] for r in st.stories(s, "2026-11-15")] == ["2026-11-01-c01", "2026-11-15-c02"]
    st.remember_stories(s, {"date": "2026-11-16", "items": []})
    assert [r["id"] for r in s["stories"]] == ["2026-11-15-c02"]


def test_without_stories_key_records_come_from_digest_files(repo):
    Path("data/digests").mkdir(parents=True)
    for date in ("2026-11-01", "2026-11-20"):
        Path(f"data/digests/{date}.json").write_text(json.dumps({"date": date, "items": [item("c03")]}), encoding="utf-8")
    assert [r["id"] for r in st.stories({"days": []}, "2026-11-21")] == ["2026-11-20-c03"]


def test_force_replaces_the_days_records():
    s = {"days": []}
    st.remember_stories(s, {"date": "2026-11-21", "items": [item("c09")]})
    up = item("c02", update={"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21"}, new="Fixed.")
    st.remember_stories(s, {"date": "2026-11-22", "items": [up, item("c05")]})
    st.remember_stories(s, {"date": "2026-11-22", "items": [item("c07")]}, force=True)
    assert [r["id"] for r in s["stories"]] == ["2026-11-21-c09", "2026-11-22-c07"]
    assert s["stories"][0]["last"] == "2026-11-21" and len(s["stories"][0]["told"]) == 1
