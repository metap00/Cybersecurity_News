"""Stage 2: score candidates against profile.md → out/ranked.json (claude-haiku-5-5)."""
import json
import sys

from brief import llm

KINDS = ["act", "learn", "know", "skip"]
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "integer"},
            "kind": {"type": "string", "enum": KINDS},
            "reason": {"type": "string"},
        },
        "required": ["id", "score", "kind", "reason"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}
FIELDS = ("id", "title", "summary", "feed", "also", "cves", "kev")


def stage():
    cands = llm.load("out/candidates.json")["candidates"]
    if not cands:
        print("[triage] no candidates; empty shortlist")
        llm.save("out/ranked.json", {"shortlist": []})
        return
    ids = [c["id"] for c in cands]

    def check(data):
        seen = {s["id"] for s in data["items"]}
        errs = [f"unknown id {i}" for i in seen - set(ids)]
        errs += [f"missing id {i}" for i in ids if i not in seen]
        errs += [f"{s['id']}: score must be 0-10" for s in data["items"] if not 0 <= s["score"] <= 10]
        return errs

    recent = [t for d in llm.recent_days() for t in d.get("titles", [])]
    user = (
        "<profile>\n" + llm.profile() + "\n</profile>\n\n"
        "<already_sent_titles>\n" + json.dumps(recent, ensure_ascii=False) + "\n</already_sent_titles>\n\n"
        "<candidates>\n" + json.dumps([{k: c.get(k) for k in FIELDS} for c in cands], ensure_ascii=False, indent=1)
        + "\n</candidates>"
    )
    data = llm.call_checked(llm.HAIKU, llm.prompt("triage"), user, SCHEMA, "low", check)
    by_id = {c["id"]: c for c in cands}
    order = {i: n for n, i in enumerate(ids)}
    scored = [s for s in data["items"] if s["id"] in by_id and s["kind"] != "skip" and s["score"] >= 6]
    scored.sort(key=lambda s: (-s["score"], order[s["id"]]))
    shortlist = [{**by_id[s["id"]], "score": s["score"], "kind": s["kind"],
                  "reason": " ".join(s["reason"].split()[:12])} for s in scored[:5]]
    llm.save("out/ranked.json", {"shortlist": shortlist})
    print(f"[triage] {len(cands)} candidates → {len(shortlist)} shortlisted")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    return llm.run(stage, "triage")


if __name__ == "__main__":
    sys.exit(main())
