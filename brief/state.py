"""data/state.json: what was sent and what was answered. Written by code only."""
import json
from datetime import date, timedelta
from pathlib import Path

PATH = Path("data/state.json")
KEEP = 90
NO_QUIZ_MODES = {"weekly", "none"}


def load(path=None) -> dict:
    p = Path(path or PATH)
    if not p.exists():
        return {"version": 1, "days": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(state, path=None) -> None:
    p = Path(path or PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["days"] = state["days"][-KEEP:]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _day(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d))


def polls(day) -> list:
    """The day's quiz polls: [{message_id, question, answered, correct, reasked}].

    Days from before the 3-question quiz had one poll in flat fields; they are converted in place.
    """
    if "polls" not in day:
        day["polls"] = [] if day.get("poll_message_id") is None else [{
            "message_id": day["poll_message_id"], "question": day.get("question"), "answered": day.get("answered"),
            "correct": day.get("correct"), "reasked": day.get("reasked", False)}]
    return day["polls"]


def has_quiz(day) -> bool:
    return day.get("mode") not in NO_QUIZ_MODES and bool(polls(day))


def score(day):
    """(right, asked) once the day's polls are closed, else None."""
    ps = polls(day)
    if not ps or any(p.get("answered") is None for p in ps):
        return None
    return sum(bool(p.get("correct")) for p in ps), len(ps)


def last_score(state, today):
    """(right, asked) of the latest closed quiz day before today, or None."""
    for d in reversed(state["days"]):
        if d["date"] < str(today) and has_quiz(d) and score(d):
            return score(d)
    return None


def mark(day) -> str:
    """✅ at least one question answered, ⬜ sent but none answered, ➖ no quiz that day."""
    if day is None or not has_quiz(day):
        return "➖"
    return "✅" if day.get("answered") else "⬜"


def last_week(state, today) -> list:
    """Entries dated in the 7 days before today, oldest first."""
    t = _day(today)
    return [d for d in state["days"] if t - timedelta(days=7) <= _day(d["date"]) < t]


def next_mode(state, today) -> str:
    t = _day(today)
    if t.weekday() == 6 and any(d.get("mode") not in NO_QUIZ_MODES for d in last_week(state, t)):
        return "weekly"
    quiz_days = [d for d in state["days"] if has_quiz(d)][-2:]
    if len(quiz_days) == 2 and not any(d.get("answered") for d in quiz_days):
        return "small"
    return "full"


def dots(state, today) -> str:
    """One mark per day for the 7 days before today, oldest first."""
    t = _day(today)
    by_date = {d["date"]: d for d in state["days"]}
    return "".join(mark(by_date.get((t - timedelta(days=i)).isoformat())) for i in range(7, 0, -1))


def streak(state) -> int:
    """Consecutive answered quiz days. ➖ days and not-yet-synced days do not break it."""
    n = 0
    for d in reversed(state["days"]):
        if not has_quiz(d) or d.get("answered") is None:
            continue
        if not d["answered"]:
            break
        n += 1
    return n
