"""Run the whole brief: sync → mode → (weekly | collect → triage → write → critique) → send.

python -m brief.run [--dry-run] [--date YYYY-MM-DD]
python -m brief.run --demo      # render examples/digest.json: no tokens, no network, no files written
"""
import argparse
import contextlib
import datetime as dt
import importlib
import io
import json
import os
import sys
from pathlib import Path


def stage(name):
    """Imported on use, so tests can put fakes in sys.modules."""
    return importlib.import_module(f"brief.{name}")


def call(name, argv):
    """Run one stage's main(argv). Returns its exit code (exceptions and SystemExit count as 1/code)."""
    print(f"[run] {name} {' '.join(argv)}".rstrip(), flush=True)
    try:
        return stage(name).main(argv) or 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:  # noqa: BLE001 - any crash stops the run
        print(f"[run] {name} crashed: {type(e).__name__}: {e}")
        return 1


def captured(name, argv):
    """call(), keeping a copy of what it printed (the rendered brief in dry-run)."""
    buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")  # reconfigure(), unlike StringIO; \n kept as-is on Windows
    with contextlib.redirect_stdout(buf):
        code = call(name, argv)
    buf.flush()
    text = buf.buffer.getvalue().decode("utf-8")
    sys.stdout.write(text)
    return code, text


def plan(mode, date, dry):
    """The stage calls after sync, in order."""
    d = ["--dry-run"] if dry else []
    if mode == "weekly":
        return [("weekly", ["--date", date]), ("deliver", ["send", "--weekly", "--date", date] + d)]
    return [("collect", []), ("triage", ["--date", date]), ("write", []),
            ("critique", ["--mode", mode, "--date", date]),
            ("deliver", ["send", "--date", date] + d)]


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary(date, mode, failed, dry, brief):
    """Markdown for the GitHub job summary, built from the out/ files."""
    c, r, g = read("out/candidates.json"), read("out/ranked.json"), read("out/digest.json")
    rows = [("date", date), ("mode", mode or "-"), ("result", f"failed at **{failed}**" if failed else "ok")]
    if c:
        feeds = c.get("feeds", [])
        rows += [("feeds OK", f"{sum(f.get('ok', False) for f in feeds)}/{len(feeds)}"),
                 ("candidates", len(c.get("candidates", [])))]
    if r:
        rows.append(("shortlisted", len(r.get("shortlist", []))))
    if g:
        rows.append(("passed", f"{len(g.get('items', []))} ({g.get('mode')})"))
    rows.append(("sent", "no (dry run)" if dry else ("no" if failed else "yes")))
    spent = getattr(sys.modules.get("brief.llm"), "spent", [])  # T2 records (model, in, out) per call
    if spent:
        rows.append(("tokens", f"{sum(s[1] for s in spent)} in / {sum(s[2] for s in spent)} out"))
    md = "### Daily brief\n\n| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
    if dry and brief:
        md += "\n#### Rendered brief\n\n```text\n" + brief.strip() + "\n```\n"
    return md


EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "digest.json"


def plain(html_text):
    """Telegram HTML → terminal text: links keep their label, tags go, entities are decoded."""
    import html
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", html_text))


def demo() -> int:
    """Render a real brief (examples/digest.json) exactly as deliver would, plus its quiz polls."""
    deliver = stage("deliver")
    digest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    today = dt.date.fromisoformat(digest["date"])
    # A made-up week of answers, so the streak footer has something to show.
    pattern = [[True, True, False], [True, False, True], [False, False, False], [True, True, True], [True, True, False]]
    days = [{"date": (today - dt.timedelta(days=len(pattern) - i)).isoformat(), "mode": "full",
             "answered": any(p), "polls": [{"answered": a, "correct": a} for a in p]} for i, p in enumerate(pattern)]
    for n, message in enumerate(deliver.render(digest, {"days": days}), 1):
        print(f"──── Telegram message {n} " + "─" * 40)
        print(plain(message) + "\n")
    for n, q in enumerate(digest["questions"], 1):
        print(f"──── Quiz poll {n}/{len(digest['questions'])} ({q['kind']}) " + "─" * 30)
        print(q["text"])
        for i, o in enumerate(q["options"]):
            print(f"  {'ABCD'[i]}) {o}")
        print(f"  ✔ {'ABCD'[q['correct']]}: {q['explanation']}\n")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m brief.run")
    ap.add_argument("--demo", action="store_true", help="render the example brief; no tokens, no network")
    ap.add_argument("--dry-run", action="store_true")
    # ponytail: UTC date equals the local date for a 04:30 UTC run; revisit if the send time moves near midnight.
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args = ap.parse_args(argv)
    if args.demo:
        return demo()

    mode, failed, brief = None, None, ""
    try:
        if not args.dry_run and call("deliver", ["sync"]):
            failed = "deliver sync"
            print("[run] stopped: stage 'deliver sync' failed")
            return 1
        st = stage("state")
        mode = st.next_mode(st.load(), dt.date.fromisoformat(args.date))
        print(f"[run] mode: {mode}")
        for name, sub in plan(mode, args.date, args.dry_run):
            if name == "deliver" and args.dry_run:
                code, brief = captured(name, sub)
            else:
                code = call(name, sub)
            if code:
                failed = name
                print(f"[run] stopped: stage '{name}' exited {code}")
                return 1
        return 0
    except Exception as e:  # noqa: BLE001 - state.load / next_mode crash
        failed = failed or "state"
        print(f"[run] stopped: {type(e).__name__}: {e}")
        return 1
    finally:
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a", encoding="utf-8") as f:
                f.write(summary(args.date, mode, failed, args.dry_run, brief))


if __name__ == "__main__":
    sys.exit(main())
