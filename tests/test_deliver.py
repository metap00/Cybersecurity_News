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
            "question": digest()["question"], "answered": answered, "correct": correct, "reasked": reasked}


def test_send_delivers_message_then_silent_quiz_and_records_state(repo):
    assert deliver.main(["send", "--date", "2026-11-21"]) == 0
    assert [m for m, _ in repo.calls] == ["sendMessage", "sendMessage", "sendPoll"]
    stories, extras, poll = (c[1] for c in repo.calls)
    assert stories["parse_mode"] == "HTML" and stories["link_preview_options"] == {"is_disabled": True}
    first = stories["text"].split("\n\n")[0]
    assert first.startswith("🔴 <b>Chrome zero-day is being exploited</b>\nAttackers are already exploiting")
    assert "<i>Why it matters to you:</i> You run Chrome" in first and ">Source</a>: The Hacker News</i>" in first
    assert "🎯 <a href=\"https://attack.mitre.org/techniques/T1187/\">T1187</a> Forced Authentication:" in stories["text"]
    assert "👤 UNC5221: China-linked" in stories["text"]
    assert extras["text"].startswith("💡 <b>Today I learned: Forced Authentication</b>")
    assert "📖 <b>Words of the day</b>\n• <b>hash</b>:" in extras["text"]
    assert "▶ Do now (1 min): ⋮ → Help → About Google Chrome → Relaunch\n<i>For: Chrome zero-day" in extras["text"]
    assert extras["text"].endswith("Done. One tap below ↓")
    assert poll["disable_notification"] is True and poll["correct_option_ids"] == [1]
    s = st.load()
    assert s["glossary"] == ["hash", "root"] and s["til"] == ["Forced Authentication"]
    d = s["days"][-1]
    assert d["poll_message_id"] == 4711 and d["answered"] is None
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
    assert len(repo.calls) == 3
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
    assert d["answered"] is True and d["correct"] is False  # tapped option 0, correct is 1


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
    assert repo.calls[0][1]["text"] == "Nothing worth your minute today. One question:"
    d.update(date="2026-11-23", mode="none", question=None)
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
    assert [m for m, _ in repo.calls] == ["sendMessage", "sendPoll", "sendPoll"]
    s = st.load()
    assert [d["reasked"] for d in s["days"][:4]] == [True, True, False, False]  # oldest two missed
    assert s["days"][-1]["mode"] == "weekly"


def test_errors_never_print_the_token(repo, capsys):
    repo.responses["sendMessage"] = 401
    assert deliver.main(["send", "--date", "2026-11-21"]) == 1
    out = capsys.readouterr().out
    assert "sendMessage failed" in out and TOKEN not in out and "42" not in out
    assert not Path("data/state.json").exists()
