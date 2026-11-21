"""Stage 3: draft every shortlisted item, a review question, glossary and TIL → out/draft.json (claude-sonnet-5-5)."""
import json
import sys

from brief import llm

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": llm.ITEM}, "review_question": llm.QUESTION,
                   **llm.EXTRAS["properties"]},
    "required": ["items", "review_question", "glossary", "til"],
    "additionalProperties": False,
}
FIELDS = ("id", "title", "summary", "feed", "kind", "cves", "kev")


def check_draft(data, ids, terms=(), tils=()):
    got = [it["id"] for it in data["items"]]
    errs = [f"unknown id {i}" for i in got if i not in ids]
    errs += [f"missing id {i}" for i in ids if i not in got]
    errs += [f"duplicate id {i}" for i in set(got) if got.count(i) > 1]
    for it in data["items"]:
        errs += llm.check_item(it)
    rq = data["review_question"]
    errs += llm.check_question(rq, "review_question") + llm.check_strings(rq, "review_question")
    return errs + llm.check_extras(data, terms, tils)


def stage():
    shortlist = llm.load("out/ranked.json")["shortlist"]
    ids = [s["id"] for s in shortlist]
    topics = sorted({d["question"]["topic"] for d in llm.recent_days() if d.get("question")})
    terms, tils = llm.history()
    user = (
        "<profile>\n" + llm.profile() + "\n</profile>\n\n"
        "<recent_question_topics>\n" + json.dumps(topics, ensure_ascii=False) + "\n</recent_question_topics>\n\n"
        "<known_terms>\n" + json.dumps(terms, ensure_ascii=False) + "\n</known_terms>\n\n"
        "<recent_til>\n" + json.dumps(tils, ensure_ascii=False) + "\n</recent_til>\n\n"
        "<shortlist>\n" + json.dumps([{k: s.get(k) for k in FIELDS} for s in shortlist], ensure_ascii=False, indent=1)
        + "\n</shortlist>"
    )
    data = llm.call_checked(llm.SONNET, llm.prompt("write"), user, SCHEMA, "medium",
                            lambda d: check_draft(d, ids, terms, tils))
    by_id = {it["id"]: it for it in data["items"]}
    llm.save("out/draft.json", {"items": [by_id[i] for i in ids], "review_question": data["review_question"],
                                "glossary": data["glossary"], "til": data["til"]})
    print(f"[write] drafted {len(ids)} items + review question + {len(data['glossary'])} terms"
          + (" + TIL" if data["til"] else ""))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    return llm.run(stage, "write")


if __name__ == "__main__":
    sys.exit(main())
