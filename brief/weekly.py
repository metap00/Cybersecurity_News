"""Sunday: name the week's pattern and pick a weekend read → out/weekly.json (claude-sonnet-5-5)."""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from brief import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string"},
        "pick": {"anyOf": [{
            "type": "object",
            "properties": {"date": {"type": "string"}, "id": {"type": "string"}, "why": {"type": "string"}},
            "required": ["date", "id", "why"], "additionalProperties": False,
        }, {"type": "null"}]},
    },
    "required": ["pattern", "pick"],
    "additionalProperties": False,
}


def week_digests(date):
    days = {(date - dt.timedelta(days=n)).isoformat() for n in range(1, 8)}
    return [llm.load(p) for p in sorted(Path("data/digests").glob("*.json")) if p.stem in days]


def stories(digests):
    """(date, id) → story with url/feed, from items and also."""
    return {(d["date"], s["id"]): s for d in digests for s in d.get("items", []) + d.get("also", [])}


def check(data, known):
    errs = []
    if llm.words(data["pattern"]) > 40:
        errs.append("pattern over 40 words")
    p = data["pick"]
    if p:
        if (p["date"], p["id"]) not in known:
            errs.append(f"pick {p['date']}/{p['id']} is not one of the listed stories")
        if llm.words(p["why"]) > 20:
            errs.append("why over 20 words")
    return errs + llm.check_strings(data, "weekly")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="brief.weekly")
    ap.add_argument("--date", required=True)
    args = ap.parse_args(argv)

    def stage():
        digests = week_digests(dt.date.fromisoformat(args.date))
        out = {"date": args.date, "pattern": None, "pick": None}
        if not digests:
            print("[weekly] no digests this week; no call")
            llm.save("out/weekly.json", out)
            return
        known = stories(digests)
        week = [{"date": d["date"],
                 "items": [{k: s.get(k) for k in ("id", "kind", "headline", "attack_id", "feed")} for s in d.get("items", [])],
                 "also": [{k: s.get(k) for k in ("id", "headline", "feed")} for s in d.get("also", [])]}
                for d in digests]
        user = ("<profile>\n" + llm.profile() + "\n</profile>\n\n<week>\n"
                + json.dumps(week, ensure_ascii=False, indent=1) + "\n</week>")
        data = llm.call_checked(llm.SONNET, llm.prompt("weekly"), user, SCHEMA, "medium", lambda d: check(d, known))
        out["pattern"] = data["pattern"]
        if data["pick"]:
            s = known[(data["pick"]["date"], data["pick"]["id"])]
            out["pick"] = {"headline": s["headline"], "url": s["url"], "feed": s["feed"], "why": data["pick"]["why"]}
        llm.save("out/weekly.json", out)
        print(f"[weekly] {len(digests)} digests → pattern + {'a pick' if out['pick'] else 'no pick'}")

    return llm.run(stage, __name__)


if __name__ == "__main__":
    sys.exit(main())
