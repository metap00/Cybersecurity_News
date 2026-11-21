"""Stage 2: score and group candidates, match them to sent stories → out/ranked.json (claude-haiku-5-5).

python -m brief.triage [--date YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import sys

from brief import llm, state

KINDS = ["act", "learn", "know", "skip"]
UPDATES = ["none", "patch", "exploited", "poc", "attribution", "victims"]
ONCE = {"patch", "exploited", "poc", "attribution"}  # sent once per story; victims may recur
MAX_UPDATES = 2  # D4: updates in one brief
NEW_WORDS, TOLD_WORDS, MAX_NAMES = 25, 120, 4
NULLABLE = {"anyOf": [{"type": "string"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "integer"},
            "kind": {"type": "string", "enum": KINDS},
            "reason": {"type": "string"},
            "dup_of": NULLABLE,
            "story": NULLABLE,
            "update": {"type": "string", "enum": UPDATES},
            "new": {"type": "string"},
            "names": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "score", "kind", "reason", "dup_of", "story", "update", "new", "names"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}
FIELDS = ("id", "title", "summary", "feed", "tier", "also", "cves", "kev")


def sent_view(r):
    """What the model sees of one sent story."""
    return {"id": r["id"], "first": r["first"], "last": r["last"], "headline": r["headline"], "names": r["names"],
            "cves": [k.upper() for k in r["keys"] if k.startswith("cve-")],
            "told": [{**t, "text": " ".join(t["text"].split()[:TOLD_WORDS])} for t in r["told"]]}


def _has(text, name):
    return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I) is not None


def seen(c, sent):
    """Sent stories that share a CVE with c, or whose name (4+ characters) is a whole word in its text. A hint."""
    text = c["title"] + " " + c["summary"]
    cves = {x.lower() for x in c.get("cves", [])}
    return [r["id"] for r in sent
            if cves & set(r["keys"]) or any(len(n) >= 4 and _has(text, n) for n in r["names"])]


def check(data, ids, sent_ids):
    got = {s["id"] for s in data["items"]}
    errs = [f"unknown id {i}" for i in got - set(ids)]
    errs += [f"missing id {i}" for i in ids if i not in got]
    for s in data["items"]:
        i = s["id"]
        if not 0 <= s["score"] <= 10:
            errs.append(f"{i}: score must be 0-10")
        if s["dup_of"] is not None and (s["dup_of"] == i or s["dup_of"] not in ids):
            errs.append(f"{i}: dup_of must be another candidate's id or null")
        if s["story"] is not None and s["story"] not in sent_ids:
            errs.append(f"{i}: story must be a sent story's id or null")
        if s["story"] is None and s["update"] != "none":
            errs.append(f"{i}: update must be none when story is null")
        if (s["update"] != "none") != bool(s["new"].strip()):
            errs.append(f"{i}: new is filled exactly when update is not none")
        if llm.words(s["new"]) > NEW_WORDS:
            errs.append(f"{i}: new over {NEW_WORDS} words")
    return errs


def groups(items, ids):
    """Candidates linked by dup_of, or naming the same sent story, as lists of ids (candidate order)."""
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i

    first_of = {}
    for s in items:
        for other in (s["dup_of"], first_of.setdefault(s["story"], s["id"]) if s["story"] else None):
            if other in parent:
                parent[root(s["id"])] = root(other)
    out = {}
    for i in ids:
        out.setdefault(root(i), []).append(i)
    return list(out.values())


def entry(members, by_id, verdict):
    """One shortlist entry for a group: the lowest tier is cited, then the longest text."""
    cs = [by_id[i] for i in members]
    cited = min(cs, key=lambda c: (c.get("tier", 2), -len(c["summary"])))
    best = max(members, key=lambda i: verdict[i]["score"])  # stable: ties go to the earlier candidate
    texts = [{k: c.get(k) for k in ("feed", "tier", "title", "summary")} for c in cs if c is not cited]
    texts += [m for c in cs for m in c.get("sources") or []]
    sources = list({(m["feed"], m["title"]): m for m in texts}.values())
    sources.sort(key=lambda m: -len(m["summary"] or ""))
    blob = " ".join(f"{m['title']} {m['summary']}" for m in [cited] + sources)
    names = [n for i in members for n in verdict[i]["names"] if n.strip() and n.casefold() in blob.casefold()]
    v = verdict[best]
    return {**cited, "score": v["score"], "kind": v["kind"], "reason": " ".join(v["reason"].split()[:12]),
            "sources": sources[:3],
            "also": list(dict.fromkeys(f for c in cs for f in [c["feed"]] + c.get("also", []) if f != cited["feed"])),
            "cves": sorted({x for c in cs for x in c.get("cves", [])}),
            "keys": list(dict.fromkeys(k for c in [cited] + cs for k in c.get("keys", []))),
            "names": list(dict.fromkeys(names))[:MAX_NAMES], "update": None, "previous": None, "_members": members}


def attach_story(e, verdict, story):
    """Update or repeat. Returns False for a repeat (logged), True otherwise."""
    told = {t["type"] for t in story["told"]}
    ups = sorted((verdict[i] for i in e["_members"] if verdict[i]["update"] != "none"), key=lambda v: -v["score"])
    ok = [v for v in ups if not (v["update"] in ONCE and v["update"] in told)]
    if not ok:
        why = f"{ups[0]['update']} already told" if ups else "nothing new"
        for i in e["_members"]:
            print(f"[triage] {i}: repeat of {story['id']}, {why}")
        return False
    e["update"] = {"story": story["id"], "type": ok[0]["update"], "since": story["last"], "hint": ok[0]["new"]}
    e["previous"] = {"headline": story["headline"], "first": story["first"], "told": story["told"]}
    return True


def shortlist(entries):
    """Best score first: score >= 6, at least 3, at most 5. Source cap (2 per feed, 1 for tier 3), waived
    only to reach 3. Max MAX_UPDATES updates. One entry per CVE: a later one's feed joins the first's `also`."""
    taken, capped, per_feed = [], [], {}

    def fits(e):
        clash = next((t for t in taken if set(t["cves"]) & set(e["cves"])), None)
        if clash:
            clash["also"] = list(dict.fromkeys(clash["also"] + [f for f in [e["feed"]] + e["also"] if f != clash["feed"]]))
            print(f"[triage] {e['id']}: shares a CVE with {clash['id']}, folded into it")
            return False
        return not (e["update"] and sum(bool(t["update"]) for t in taken) >= MAX_UPDATES)

    for e in entries:
        if len(taken) == 5 or (len(taken) >= 3 and e["score"] < 6):
            break
        if per_feed.get(e["feed"], 0) >= (1 if e.get("tier", 2) == 3 else 2):
            capped.append(e)
            continue
        if fits(e):
            per_feed[e["feed"]] = per_feed.get(e["feed"], 0) + 1
            taken.append(e)
    for e in capped:
        if len(taken) >= 3:
            break
        if fits(e):
            taken.append(e)
    taken.sort(key=entries.index)
    return taken


def stage(today):
    cands = llm.load("out/candidates.json")["candidates"]
    if not cands:
        print("[triage] no candidates; empty shortlist")
        llm.save("out/ranked.json", {"shortlist": []})
        return
    ids = [c["id"] for c in cands]
    sent = state.stories(state.load(), today)
    stories = {r["id"]: r for r in sent}
    hints = {c["id"]: seen(c, sent) for c in cands}
    user = (
        "<profile>\n" + llm.profile() + "\n</profile>\n\n"
        "<sent_stories>\n" + json.dumps([sent_view(r) for r in sent], ensure_ascii=False, indent=1)
        + "\n</sent_stories>\n\n"
        "<candidates>\n" + json.dumps([{**{k: c.get(k) for k in FIELDS}, "seen": hints[c["id"]]} for c in cands],
                                      ensure_ascii=False, indent=1) + "\n</candidates>"
    )
    data = llm.call_checked(llm.HAIKU, llm.prompt("triage"), user, SCHEMA, "low",
                            lambda d: check(d, ids, set(stories)))
    verdict = {s["id"]: s for s in data["items"]}
    by_id = {c["id"]: c for c in cands}
    for i in ids:
        if hints[i] and verdict[i]["story"] is None:
            print(f"[triage] {i}: shares a CVE or name with {', '.join(hints[i])}, judged a different story")
    entries = []
    for g in groups(data["items"], ids):
        e = entry(g, by_id, verdict)
        story = next((verdict[i]["story"] for i in g if verdict[i]["story"]), None)
        if story and not attach_story(e, verdict, stories[story]):
            continue
        if len(g) > 1:
            print(f"[triage] {', '.join(g)}: one event, cited to {e['feed']}")
        if e["kind"] != "skip" and e["score"] >= 4:
            entries.append(e)
    entries.sort(key=lambda e: (-e["score"], ids.index(e["_members"][0])))
    short = [{k: v for k, v in e.items() if k != "_members"} for e in shortlist(entries)]
    llm.save("out/ranked.json", {"shortlist": short})
    print(f"[triage] {len(cands)} candidates → {len(entries)} entries → {len(short)} shortlisted")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="brief.triage")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args = ap.parse_args(argv)
    return llm.run(lambda: stage(args.date), "triage")


if __name__ == "__main__":
    sys.exit(main())
