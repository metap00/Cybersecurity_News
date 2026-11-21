"""Run the whole brief: sync → mode → (weekly | collect → triage → write → critique) → send.

python -m brief.run [--dry-run] [--date YYYY-MM-DD]
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
    buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")  # has reconfigure(), unlike StringIO
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
    return [("collect", []), ("triage", []), ("write", []),
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
    spent = getattr(sys.modules.get("brief.llm"), "spent", [])  # T2 records (model, in, out, $) per call
    if spent:
        rows.append(("tokens", f"{sum(s[1] for s in spent)} in / {sum(s[2] for s in spent)} out"
                               f" (${sum(s[3] for s in spent):.4f})"))
    md = "### Daily brief\n\n| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
    if dry and brief:
        md += "\n#### Rendered brief\n\n```text\n" + brief.strip() + "\n```\n"
    return md


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m brief.run")
    ap.add_argument("--dry-run", action="store_true")
    # ponytail: UTC date equals the local date for a 04:30 UTC run; revisit if the send time moves near midnight.
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args = ap.parse_args(argv)

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
