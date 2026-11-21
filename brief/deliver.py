"""Telegram delivery: close yesterday's quiz, send today's brief + quiz, keep state.

python -m brief.deliver sync [--dry-run]
python -m brief.deliver send [--weekly] [--dry-run] [--force] --date YYYY-MM-DD
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from brief import state as st

OUT = Path("out")
DIGESTS = Path("data/digests")
MAX_WORDS = 120
MAX_WEEKLY_WORDS = 100
MARKERS = {"act": "🔴", "learn": "🟠", "know": "🟡"}


class TelegramError(Exception):
    def __init__(self, method, description, code=None):
        super().__init__(f"{method}: {description}")
        self.method, self.description, self.code = method, description, code


def api(method, **params):
    """POST one Bot API call. Errors carry the method and Telegram's description only, never the token."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise TelegramError(method, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps({"chat_id": chat, **params}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))["result"]
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:
            desc = ""
        raise TelegramError(method, desc or f"HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, TimeoutError) as e:
        # e.reason never contains the URL, so the token stays out of the logs
        raise TelegramError(method, f"network error: {getattr(e, 'reason', e)}") from None


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def link(url, text) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(text)}</a>'


def attack_url(tid) -> str:
    return f"https://attack.mitre.org/techniques/{tid.replace('.', '/')}/"


def visible_words(text) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def poll_payload(q) -> dict:
    return {
        "question": q["text"],
        "options": [{"text": o} for o in q["options"]],
        "type": "quiz",
        "correct_option_ids": [q["correct"]],
        "explanation": q["explanation"],
        "disable_notification": True,
    }


def quiz_errors(q) -> list:
    """Telegram's own hard limits; the API rejects anything over them."""
    errs = []
    if not 1 <= len(q["text"]) <= 300:
        errs.append("question must be 1-300 characters")
    if len(q["options"]) != 3 or not all(1 <= len(o) <= 100 for o in q["options"]):
        errs.append("need 3 options of 1-100 characters")
    if not 0 <= q["correct"] < len(q["options"]):
        errs.append("correct index out of range")
    if len(q["explanation"]) > 200:
        errs.append("explanation over 200 characters")
    return errs


def footer(s, today) -> str:
    if not s["days"]:
        return "Done. One tap below ↓"
    return f"Done. Last 7 days {st.dots(s, today)} · streak {st.streak(s)} · one tap below ↓"


def render(digest, s) -> str:
    if digest["mode"] == "quiz_only":
        return "Nothing worth your minute today. One question:"
    action = digest.get("action")
    blocks = []
    for it in digest["items"]:
        lines = [f"{MARKERS.get(it['kind'], '🟡')} <b>{esc(it['headline'])}</b>", esc(it["you"])]
        if action and action.get("item_id") == it["id"]:
            lines.append(f"▶ Do now ({int(action['minutes'])} min): {esc(action['text'])}")
        src = f"{link(it['url'], it['feed'])} ↗"
        if it.get("attack_id"):
            src += f" · {link(attack_url(it['attack_id']), it['attack_id'])} ↗"
        lines.append(src)
        blocks.append("\n".join(lines))
    blocks.append(footer(s, digest["date"]))
    return "\n\n".join(blocks)


def render_weekly(weekly, s, today, n_reask) -> str:
    week = [d for d in st.last_week(s, today) if st.has_quiz(d)]
    read = [d for d in week if d.get("answered")]
    right = [d for d in read if d.get("correct")]
    lines = [f"📅 Your week: read {len(read)} of {len(week)} · {len(right)} of {len(read)} right · streak {st.streak(s)}"]
    if weekly.get("pattern"):
        lines.append(f"Pattern: {esc(weekly['pattern'])}")
    pick = weekly.get("pick")
    if pick:
        lines.append(f"Weekend pick (15 min): {link(pick['url'], pick['headline'])} ↗ {esc(pick['feed'])}. {esc(pick['why'])}")
    if n_reask:
        lines.append("Two questions you missed come next ↓" if n_reask == 2 else "One question you missed comes next ↓")
    return "\n".join(lines)


def to_reask(s, today) -> list:
    return [
        d for d in st.last_week(s, today)
        if st.has_quiz(d) and d.get("question") and not d.get("reasked")
        and not (d.get("answered") and d.get("correct"))
    ][:2]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def send_message(text):
    api("sendMessage", text=text, parse_mode="HTML", link_preview_options={"is_disabled": True})


def put_day(s, entry, force):
    s["days"] = [d for d in s["days"] if d["date"] != entry["date"]] if force else s["days"]
    s["days"].append(entry)
    s["days"].sort(key=lambda d: d["date"])


def cmd_sync(args) -> int:
    s = st.load()
    pending = [d for d in s["days"] if d.get("poll_message_id") is not None and d.get("answered") is None]
    if not pending:
        print("sync: no open quiz")
        return 0
    day = pending[-1]
    if args.dry_run:
        print(f"sync (dry run): would close the quiz of {day['date']}")
        return 0
    try:
        poll = api("stopPoll", message_id=day["poll_message_id"])
        day["answered"] = poll["total_voter_count"] > 0
        day["correct"] = poll["options"][day["question"]["correct"]]["voter_count"] > 0
    except TelegramError as e:
        if e.code != 400:  # 400 = already closed or gone; anything else is a real failure
            print(f"sync: {e.method} failed: {e.description}")
            return 1
        print(f"sync: quiz of {day['date']} already closed or gone ({e.description})")
        day["answered"], day["correct"] = False, False
    st.save(s)
    print(f"sync: {day['date']} answered={day['answered']} correct={day['correct']}")
    return 0


def cmd_send(args) -> int:
    s = st.load()
    if any(d["date"] == args.date for d in s["days"]) and not args.force:
        print(f"send: {args.date} was already sent; use --force to send again")
        return 1
    return send_weekly(args, s) if args.weekly else send_daily(args, s)


def send_daily(args, s) -> int:
    digest = read_json(OUT / "digest.json")
    if digest.get("date") != args.date:
        print(f"send: out/digest.json is for {digest.get('date')}, not {args.date}")
        return 1
    mode, q = digest["mode"], digest.get("question")
    entry = {
        "date": args.date, "mode": mode, "sent_at": now_iso(),
        "keys": sorted({k for it in digest.get("items", []) for k in it.get("keys", [])}),
        "titles": [it["headline"] for it in digest.get("items", [])],
        "poll_message_id": None, "question": q if mode != "none" else None,
        "answered": None, "correct": None, "reasked": False,
    }
    if mode == "none":
        print("send: mode none, nothing to send")
        if not args.dry_run:
            put_day(s, entry, args.force)
            st.save(s)
        return 0

    text = render(digest, s)
    words = visible_words(text)
    if words > MAX_WORDS:
        print(f"send: brief has {words} words, cap is {MAX_WORDS}; nothing sent")
        return 1
    if errs := quiz_errors(q):
        print(f"send: quiz rejected: {'; '.join(errs)}; nothing sent")
        return 1
    payload = poll_payload(q)
    if args.dry_run:
        print(text)
        print(f"\n--- {words} words ---\nsendPoll:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        send_message(text)
        entry["poll_message_id"] = api("sendPoll", **payload)["message_id"]
    except TelegramError as e:
        print(f"send: {e.method} failed: {e.description}")
        return 1
    entry["sent_at"] = now_iso()
    put_day(s, entry, args.force)
    st.save(s)
    DIGESTS.mkdir(parents=True, exist_ok=True)
    with open(DIGESTS / f"{args.date}.json", "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"send: {args.date} delivered ({words} words, {len(digest['items'])} items)")
    return 0


def send_weekly(args, s) -> int:
    weekly = read_json(OUT / "weekly.json")
    reask = to_reask(s, args.date)
    text = render_weekly(weekly, s, args.date, len(reask))
    words = visible_words(text)
    if words > MAX_WEEKLY_WORDS:
        print(f"send: recap has {words} words, cap is {MAX_WEEKLY_WORDS}; nothing sent")
        return 1
    payloads = [poll_payload(d["question"]) for d in reask]
    if args.dry_run:
        print(text)
        print(f"\n--- {words} words ---")
        for p in payloads:
            print("sendPoll:\n" + json.dumps(p, ensure_ascii=False, indent=2))
        return 0

    try:
        send_message(text)
        for d, p in zip(reask, payloads):
            api("sendPoll", **p)
            d["reasked"] = True
    except TelegramError as e:
        print(f"send: {e.method} failed: {e.description}")
        st.save(s)  # keep any reasked marks already earned; the day itself is not recorded
        return 1
    put_day(s, {
        "date": args.date, "mode": "weekly", "sent_at": now_iso(), "keys": [], "titles": [],
        "poll_message_id": None, "question": None, "answered": None, "correct": None, "reasked": False,
    }, args.force)
    st.save(s)
    print(f"send: weekly recap {args.date} delivered ({words} words, {len(reask)} re-asked)")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m brief.deliver")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--dry-run", action="store_true")
    p_send = sub.add_parser("send")
    p_send.add_argument("--date", required=True)
    p_send.add_argument("--weekly", action="store_true")
    p_send.add_argument("--dry-run", action="store_true")
    p_send.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return cmd_sync(args) if args.cmd == "sync" else cmd_send(args)


if __name__ == "__main__":
    sys.exit(main())
