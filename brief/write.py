"""Stage 3: draft every shortlisted item, a review question, glossary and TIL → out/draft.json (claude-sonnet-5-5)."""
import json
import sys

from brief import llm

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": llm.ITEM}, "review_question": llm.QUESTION,
                   "term_question": llm.QUESTION, "soc_question": llm.QUESTION, **llm.EXTRAS["properties"]},
    "required": ["items", "review_question", "term_question", "soc_question", "glossary", "til"],
    "additionalProperties": False,
}
FIELDS = ("id", "title", "summary", "feed", "kind", "cves", "kev")
QUESTIONS = ("review_question", "term_question", "soc_question")
SOURCE_FIELDS = ("feed", "tier", "title", "summary")


def model_view(s):
    """What the models see of one shortlist entry. sources/update/previous are optional (T2, T3)."""
    return {**{k: s.get(k) for k in FIELDS},
            "sources": [{k: m.get(k) for k in SOURCE_FIELDS} for m in s.get("sources") or []],
            "update": s.get("update"), "previous": s.get("previous")}


def check_draft(data, ids, terms=(), tils=(), updates=()):
    got = [it["id"] for it in data["items"]]
    errs = [f"unknown id {i}" for i in got if i not in ids]
    errs += [f"missing id {i}" for i in ids if i not in got]
    errs += [f"duplicate id {i}" for i in set(got) if got.count(i) > 1]
    for it in data["items"]:
        errs += llm.check_item(it, it["id"] in updates)
    for k in QUESTIONS:
        errs += llm.check_question(data[k], k) + llm.check_strings(data[k], k)
    return errs + llm.check_extras(data, terms, tils)


def stage():
    shortlist = llm.load("out/ranked.json")["shortlist"]
    ids = [s["id"] for s in shortlist]
    updates = {s["id"] for s in shortlist if s.get("update")}
    topics = llm.recent_topics()
    terms, tils = llm.history()
    user = (
        "<profile>\n" + llm.profile() + "\n</profile>\n\n"
        "<recent_question_topics>\n" + json.dumps(topics, ensure_ascii=False) + "\n</recent_question_topics>\n\n"
        "<known_terms>\n" + json.dumps(terms, ensure_ascii=False) + "\n</known_terms>\n\n"
        "<recent_til>\n" + json.dumps(tils, ensure_ascii=False) + "\n</recent_til>\n\n"
        "<shortlist>\n" + json.dumps([model_view(s) for s in shortlist], ensure_ascii=False, indent=1)
        + "\n</shortlist>"
    )
    data = llm.call_checked(llm.SONNET, llm.prompt("write"), user, SCHEMA, "medium",
                            lambda d: check_draft(d, ids, terms, tils, updates), fatal=lambda e: " id " in f" {e}")
    by_id = {it["id"]: it for it in data["items"]}
    llm.save("out/draft.json", {"items": [by_id[i] for i in ids], **{k: data[k] for k in QUESTIONS},
                                "glossary": data["glossary"], "til": data["til"]})
    print(f"[write] drafted {len(ids)} items + 3 extra questions + {len(data['glossary'])} terms"
          + (" + TIL" if data["til"] else ""))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    return llm.run(stage, "write")


if __name__ == "__main__":
    sys.exit(main())
