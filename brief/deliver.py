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

from brief import llm, state as st

OUT = Path("out")
DIGESTS = Path("data/digests")
MAX_WORDS = 750
NEXT = "\n\n— next message —\n\n"  # dry-run marker between messages
MAX_WEEKLY_WORDS = 150
MAX_CHARS = 4096  # Telegram's limit for one message
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
    if len(q["options"]) not in (3, 4) or not all(1 <= len(o) <= 100 for o in q["options"]):
        errs.append("need 3 or 4 options of 1-100 characters")
    if not 0 <= q["correct"] < len(q["options"]):
        errs.append("correct index out of range")
    if len(q["explanation"]) > 200:
        errs.append("explanation over 200 characters")
    return errs


def footer(s, today, n=1) -> str:
    below = "one tap below ↓" if n == 1 else f"{n} quick questions below ↓"
    if not s["days"]:
        return f"Done. {below[0].upper()}{below[1:]}"
    last = st.last_score(s, today)
    yesterday = f"Last quiz {last[0]}/{last[1]} · " if last else ""
    return f"Done. {yesterday}Last 7 days {st.dots(s, today)} · streak {st.streak(s)} · {below}"


def render(digest, s) -> list:
    """Two messages: the stories, then Today I Learned + glossary + Do now + streak. The quiz follows."""
    n = len(digest.get("questions") or [])
    if digest["mode"] == "quiz_only":
        return ["Nothing worth your minute today. " + ("One question:" if n == 1 else f"{n} questions:")]
    stories = []
    for it in digest["items"]:
        up = it.get("update")
        if up:  # PLAN-sources section 4.4: the reminder sits in "summary"
            since = datetime.strptime(up["since"], "%Y-%m-%d")
            lines = [f"🔄 <b>Update: {esc(it['headline'])}</b>",
                     f"<i>What's new since {since.day} {since:%b}:</i> {esc(it.get('new') or '')}",
                     f"<i>Reminder:</i> {esc(it['summary'])}"]
        else:
            lines = [f"{MARKERS.get(it['kind'], '🟡')} <b>{esc(it['headline'])}</b>", esc(it["summary"])]
        if it.get("attack_id") and it.get("attack_note"):
            lines.append(f"🎯 {link(attack_url(it['attack_id']), it['attack_id'])} {esc(it['attack_note'])}")
        if it.get("actor"):
            lines.append(f"👤 {esc(it['actor'])}")
        lines.append(f"<i>Why it matters to you:</i> {esc(it['you'])}")
        lines.append(f"<i>{link(it['url'], 'Source')}: {esc(it['feed'])}</i>")
        stories.append("\n".join(lines))
    extras = []
    til = digest.get("til")
    if til:
        extras.append(f"💡 <b>Today I learned: {esc(til['concept'])}</b>\n{esc(til['text'])}")
    if digest.get("glossary"):
        extras.append("📖 <b>Words of the day</b>\n" + "\n".join(
            f"• <b>{esc(g['term'])}</b>: {esc(g['meaning'])}" for g in digest["glossary"]))
    action = digest.get("action")
    if action:
        about = next((it["headline"] for it in digest["items"] if it["id"] == action.get("item_id")), None)
        extras.append(f"▶ Do now ({int(action['minutes'])} min): {esc(action['text'])}"
                      + (f"\n<i>For: {esc(about)}</i>" if about else ""))
    extras.append(footer(s, digest["date"], n))
    return ["\n\n".join(stories), "\n\n".join(extras)] if stories else ["\n\n".join(extras)]


def remember(s, digest):
    """Keep the last glossary terms and TIL concepts so they are not taught twice."""
    terms, tils = llm.history()
    s["glossary"] = (terms + [g["term"] for g in digest.get("glossary") or []])[-llm.KEEP_TERMS:]
    s["til"] = (tils + ([digest["til"]["concept"]] if digest.get("til") else []))[-llm.KEEP_TIL:]


def render_weekly(weekly, s, today, n_reask) -> str:
    week = [d for d in st.last_week(s, today) if st.has_quiz(d)]
    read = [d for d in week if d.get("answered")]
    answered = [p for d in week for p in st.polls(d) if p.get("answered")]
    right = [p for p in answered if p.get("correct")]
    blocks = [f"📅 Your week: read {len(read)} of {len(week)} · {len(right)} of {len(answered)} right · streak {st.streak(s)}"]
    if weekly.get("pattern"):
        blocks.append(f"<b>The week's pattern</b>\n{esc(weekly['pattern'])}")
    pick = weekly.get("pick")
    if pick:
        blocks.append(f"<b>Weekend read (15 min): {esc(pick['headline'])}</b>\n{esc(pick['why'])}\n"
                      f"<i>{link(pick['url'], 'Source')}: {esc(pick['feed'])}</i>")
    if n_reask:
        blocks.append("One question you missed comes next ↓" if n_reask == 1
                      else f"{n_reask} questions you missed or got wrong come next ↓")
    return "\n\n".join(blocks)


MAX_REASK = 3


def to_reask(s, today) -> list:
    """Polls of the last 7 days that were missed or wrong and not re-asked yet, oldest first."""
    return [
        p for d in st.last_week(s, today) if st.has_quiz(d) for p in st.polls(d)
        if p.get("question") and not p.get("reasked") and not (p.get("answered") and p.get("correct"))
    ][:MAX_REASK]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def chunks(text, limit=MAX_CHARS) -> list:
    """Split at blank lines (between items, so no HTML tag is cut) into messages of at most `limit` characters."""
    out = []
    for block in text.split("\n\n"):
        if out and len(out[-1]) + 2 + len(block) <= limit:
            out[-1] += "\n\n" + block
        else:
            out.append(block)
    return out


def send_message(text):
    for part in chunks(text):
        api("sendMessage", text=part, parse_mode="HTML", link_preview_options={"is_disabled": True})


def put_day(s, entry, force):
    s["days"] = [d for d in s["days"] if d["date"] != entry["date"]] if force else s["days"]
    s["days"].append(entry)
    s["days"].sort(key=lambda d: d["date"])


def cmd_sync(args) -> int:
    """Close the open polls of the latest quiz day and record each answer. A day counts as read if any was answered."""
    s = st.load()
    pending = [d for d in s["days"] if any(p.get("answered") is None for p in st.polls(d))]
    if not pending:
        print("sync: no open quiz")
        return 0
    day = pending[-1]
    if args.dry_run:
        print(f"sync (dry run): would close {len(st.polls(day))} poll(s) of {day['date']}")
        return 0
    for p in st.polls(day):
        if p.get("answered") is not None:
            continue
        try:
            poll = api("stopPoll", message_id=p["message_id"])
            p["answered"] = poll["total_voter_count"] > 0
            p["correct"] = poll["options"][p["question"]["correct"]]["voter_count"] > 0
        except TelegramError as e:
            if e.code != 400:  # 400 = already closed or gone; anything else is a real failure
                print(f"sync: {e.method} failed: {e.description}")
                st.save(s)  # keep the polls already closed
                return 1
            print(f"sync: a poll of {day['date']} was already closed or gone ({e.description})")
            p["answered"], p["correct"] = False, False
    day["answered"] = any(p["answered"] for p in st.polls(day))
    right, asked = st.score(day)
    st.save(s)
    print(f"sync: {day['date']} answered={day['answered']} score={right}/{asked}")
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
    mode, questions = digest["mode"], digest.get("questions") or []
    entry = {
        "date": args.date, "mode": mode, "sent_at": now_iso(),
        "keys": sorted({k for it in digest.get("items", []) for k in it.get("keys", [])}),
        "titles": [it["headline"] for it in digest.get("items", [])],
        "polls": [], "answered": None,
    }
    if mode == "none":
        print("send: mode none, nothing to send")
        if not args.dry_run:
            put_day(s, entry, args.force)
            st.save(s)
        return 0

    messages = render(digest, s)
    words = visible_words("\n\n".join(messages))
    if words > MAX_WORDS:
        print(f"send: brief has {words} words, cap is {MAX_WORDS}; nothing sent")
        return 1
    if errs := [f"question {n}: {e}" for n, q in enumerate(questions, 1) for e in quiz_errors(q)]:
        print(f"send: quiz rejected: {'; '.join(errs)}; nothing sent")
        return 1
    payloads = [poll_payload(q) for q in questions]
    if args.dry_run:
        print(NEXT.join(messages))
        print(f"\n--- {words} words, {sum(len(chunks(m)) for m in messages)} messages, {len(payloads)} polls ---")
        for p in payloads:
            print("sendPoll:\n" + json.dumps(p, ensure_ascii=False, indent=2))
        return 0

    try:
        for m in messages:
            send_message(m)
        for q, p in zip(questions, payloads):
            entry["polls"].append({"message_id": api("sendPoll", **p)["message_id"], "question": q,
                                   "answered": None, "correct": None, "reasked": False})
    except TelegramError as e:
        print(f"send: {e.method} failed: {e.description}")
        if entry["polls"]:  # the brief is out: record it so sync closes those polls and nothing is sent twice
            put_day(s, entry, args.force)
            st.save(s)
        return 1
    entry["sent_at"] = now_iso()
    put_day(s, entry, args.force)
    remember(s, digest)
    st.remember_stories(s, digest, args.force)
    st.save(s)
    DIGESTS.mkdir(parents=True, exist_ok=True)
    with open(DIGESTS / f"{args.date}.json", "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"send: {args.date} delivered ({words} words, {len(digest['items'])} items, {len(entry['polls'])} polls)")
    return 0


def send_weekly(args, s) -> int:
    weekly = read_json(OUT / "weekly.json")
    reask = to_reask(s, args.date)
    text = render_weekly(weekly, s, args.date, len(reask))
    words = visible_words(text)
    if words > MAX_WEEKLY_WORDS:
        print(f"send: recap has {words} words, cap is {MAX_WEEKLY_WORDS}; nothing sent")
        return 1
    payloads = [poll_payload(p["question"]) for p in reask]
    if args.dry_run:
        print(text)
        print(f"\n--- {words} words ---")
        for p in payloads:
            print("sendPoll:\n" + json.dumps(p, ensure_ascii=False, indent=2))
        return 0

    try:
        send_message(text)
        for poll, p in zip(reask, payloads):
            api("sendPoll", **p)
            poll["reasked"] = True
    except TelegramError as e:
        print(f"send: {e.method} failed: {e.description}")
        st.save(s)  # keep any reasked marks already earned; the day itself is not recorded
        return 1
    put_day(s, {
        "date": args.date, "mode": "weekly", "sent_at": now_iso(), "keys": [], "titles": [],
        "polls": [], "answered": None,
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
