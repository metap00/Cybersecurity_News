"""Stage 4: check drafts against the feed text, fix or drop, pick → out/digest.json (claude-opus-5-5)."""
import argparse
import json
import sys

from brief import llm

VERDICT = {"type": "string", "enum": ["pass", "fixed", "drop"]}
ISSUES = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "verdict": VERDICT, "issues": ISSUES,
                           "fixed": {"anyOf": [llm.ITEM, {"type": "null"}]}},
            "required": ["id", "verdict", "issues", "fixed"],
            "additionalProperties": False,
        }},
        "review": {
            "type": "object",
            "properties": {"verdict": VERDICT, "issues": ISSUES,
                           "fixed": {"anyOf": [llm.QUESTION, {"type": "null"}]}},
            "required": ["verdict", "issues", "fixed"],
            "additionalProperties": False,
        },
        "extras": {
            "type": "object",
            "properties": {"verdict": VERDICT, "issues": ISSUES,
                           "fixed": {"anyOf": [llm.EXTRAS, {"type": "null"}]}},
            "required": ["verdict", "issues", "fixed"],
            "additionalProperties": False,
        },
    },
    "required": ["items", "review", "extras"],
    "additionalProperties": False,
}
SOURCE = ("id", "title", "summary", "feed", "also", "cves", "kev", "kind")


def check_verdicts(data, ids):
    got = [v["id"] for v in data["items"]]
    errs = [f"unknown id {i}" for i in got if i not in ids]
    errs += [f"no verdict for {i}" for i in ids if i not in got]
    errs += [f"duplicate verdict for {i}" for i in set(got) if got.count(i) > 1]
    errs += [f"{v['id']}: verdict 'fixed' needs the fixed item" for v in data["items"]
             if v["verdict"] == "fixed" and v["fixed"] is None]
    errs += [f"{k}: verdict 'fixed' needs the fixed {k}" for k in ("review", "extras")
             if data[k]["verdict"] == "fixed" and data[k]["fixed"] is None]
    return errs


def apply(verdict, draft):
    """Return the final item text, or None when dropped (a fix that breaks a cap is a drop)."""
    if verdict["verdict"] == "drop":
        return None
    item = draft if verdict["verdict"] == "pass" else {**verdict["fixed"], "id": draft["id"]}
    errs = llm.check_item(item)
    if errs:
        print(f"[critique] dropping {draft['id']}: " + "; ".join(errs))
        return None
    return item


def apply_review(review, rq):
    if review["verdict"] == "drop":
        return None
    q = rq if review["verdict"] == "pass" else review["fixed"]
    errs = llm.check_question(q, "review_question") + llm.check_strings(q, "review_question")
    if errs:
        print("[critique] dropping review question: " + "; ".join(errs))
        return None
    return q


def apply_extras(verdict, draft, picked):
    """Glossary + TIL after review. Glossary keeps only terms that appear in the picked items."""
    none = {"glossary": [], "til": None}
    if verdict["verdict"] == "drop":
        return none
    ex = {"glossary": draft.get("glossary", []), "til": draft.get("til")} if verdict["verdict"] == "pass" else verdict["fixed"]
    errs = llm.check_extras(ex, *llm.history())
    if errs:
        print("[critique] dropping glossary and TIL: " + "; ".join(errs))
        return none
    text = " ".join(" ".join(filter(None, (it["headline"], it["summary"], it["you"], it.get("attack_note"),
                                           it.get("actor"), (it.get("action") or {}).get("text"))))
                    for it in picked).casefold()
    return {"glossary": [g for g in ex["glossary"] if g["term"].casefold() in text], "til": ex["til"]}


MAX_ITEMS, MIN_ITEMS, BUDGET = 5, 3, 700  # deliver.MAX_WORDS (750) is the hard cap
OVERHEAD = 230  # worst case outside the items: TIL, glossary, the action line, the footer


def item_words(it):
    return 8 + sum(llm.words(it.get(k) or "") for k in ("headline", "summary", "you", "attack_note", "actor"))


def pick(passing, mode):
    """Rank order. Small mode: 1. Full: at least 3 (the caps make 3 fit), then more while under the word budget."""
    if mode == "small":
        return passing[:1]
    picked, total = [], OVERHEAD
    for it in passing[:MAX_ITEMS]:
        if len(picked) >= MIN_ITEMS and total + item_words(it) > BUDGET:
            break
        picked.append(it)
        total += item_words(it)
    return picked


def build(date, mode, shortlist, draft, verdicts):
    """Pure code: verdicts → digest dict (contract in PLAN section 8)."""
    src = {s["id"]: s for s in shortlist}
    by_id = {v["id"]: v for v in verdicts["items"]}
    passing = [it for it in (apply(by_id[d["id"]], d) for d in draft["items"]) if it]
    picked = pick(passing, mode)
    rest = passing[len(picked):len(picked) + 2]
    items = [{"id": it["id"], "kind": src[it["id"]]["kind"], "headline": it["headline"],
              "summary": it["summary"], "you": it["you"], "attack_id": it["attack_id"],
              "attack_note": it.get("attack_note"), "actor": it.get("actor"),
              "url": src[it["id"]]["url"], "feed": src[it["id"]]["feed"],
              "keys": src[it["id"]]["keys"]} for it in picked]
    act = next((it for it in picked if src[it["id"]]["kind"] == "act" and it["action"]), None)
    if act is None and picked and picked[0]["action"]:
        act = picked[0]
    rq = apply_review(verdicts["review"], draft["review_question"])
    if picked:
        question = picked[0]["question"]
    else:
        mode, question = ("quiz_only", rq) if rq else ("none", None)
    return {
        "date": date,
        "mode": mode,
        "items": items,
        "action": {"item_id": act["id"], **act["action"]} if act else None,
        "question": question,
        **apply_extras(verdicts["extras"], draft, picked),
        "also": [{"id": it["id"], "headline": it["headline"], "url": src[it["id"]]["url"],
                  "feed": src[it["id"]]["feed"]} for it in rest],
    }


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="brief.critique")
    ap.add_argument("--mode", choices=["full", "small"], default="full")
    ap.add_argument("--date", required=True)
    args = ap.parse_args(argv)

    def stage():
        shortlist = llm.load("out/ranked.json")["shortlist"]
        draft = llm.load("out/draft.json")
        ids = [d["id"] for d in draft["items"]]
        src = {s["id"]: {k: s.get(k) for k in SOURCE} for s in shortlist}
        user = (
            "<profile>\n" + llm.profile() + "\n</profile>\n\n"
            "<sources>\n" + json.dumps([src[i] for i in ids], ensure_ascii=False, indent=1) + "\n</sources>\n\n"
            "<drafts>\n" + json.dumps(draft, ensure_ascii=False, indent=1) + "\n</drafts>"
        )
        verdicts = llm.call_checked(llm.OPUS, llm.prompt("critique"), user, SCHEMA, "medium",
                                    lambda d: check_verdicts(d, ids))
        for v in verdicts["items"]:
            print(f"[critique] {v['id']}: {v['verdict']}" + (f" ({'; '.join(v['issues'])})" if v["issues"] else ""))
        digest = build(args.date, args.mode, shortlist, draft, verdicts)
        llm.save("out/digest.json", digest)
        print(f"[critique] mode {digest['mode']}, {len(digest['items'])} items picked")

    return llm.run(stage, "critique")


if __name__ == "__main__":
    sys.exit(main())
