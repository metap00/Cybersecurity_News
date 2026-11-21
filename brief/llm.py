"""Shared model plumbing for the T2 stages: the one model call (Claude Code CLI), caps, file helpers."""
import datetime as dt
import json
import re
import subprocess
import tempfile
from pathlib import Path

HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
ATTACK_RE = re.compile(r"^T\d{4}(\.\d{3})?$")
FORBIDDEN = ("http", "www.", "<")
# Caps (PLAN section 3.2), in words unless noted
HEADLINE, SUMMARY_MIN, SUMMARY, YOU, NOTE, ACTION = 12, 40, 80, 15, 25, 14
QUESTION_WORDS, OPTION, EXPLANATION_CHARS = 30, 8, 200
GLOSSARY_MAX, MEANING, TIL_MIN, TIL = 6, 20, 30, 60
NEW, REMINDER_MIN, REMINDER = 30, 15, 40  # update items: what's-new line, reminder (PLAN-sources section 6)
KEEP_TERMS, KEEP_TIL = 50, 7  # glossary terms and TIL concepts never repeated
TIMEOUT = 900  # seconds per CLI call

spent = []  # (model, in_tokens, out_tokens) per call, for the stage summary


class Refused(RuntimeError):
    pass


class Invalid(RuntimeError):
    pass


def claude(model, system, user, schema, effort) -> dict:
    """Run `claude -p` once (the owner's subscription login) and return its JSON result.

    No tools, no MCP, no skills, no session saved. It runs in an empty temp dir so no CLAUDE.md is read.
    """
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--effort", effort,
           "--system-prompt", system, "--json-schema", json.dumps(schema), "--tools", "",
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"]
    with tempfile.TemporaryDirectory() as cwd:
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                           cwd=cwd, timeout=TIMEOUT)
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise RuntimeError(f"claude CLI exited {p.returncode}: {(p.stderr or p.stdout).strip()[:300]}") from None


def call(model, system, user, schema, effort) -> dict:
    """One schema-constrained call. Refusal: Haiku re-runs on Sonnet, Sonnet/Opus raise Refused."""
    r = claude(model, system, user, schema, effort)
    u = r.get("usage") or {}
    tin = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    tout = u.get("output_tokens") or 0
    spent.append((model, tin, tout))
    print(f"[llm] {model}: {tin} in / {tout} out tokens")
    if r.get("stop_reason") == "refusal":
        if model == HAIKU:
            print("[llm] Haiku refused; re-running once on Sonnet")
            return call(SONNET, system, user, schema, effort)
        raise Refused(f"{model} refused")
    if r.get("stop_reason") == "max_tokens":
        raise Invalid(f"{model} hit max_tokens")
    if r.get("is_error"):
        raise RuntimeError(f"claude CLI: {str(r.get('result'))[:300]}")
    out = r.get("structured_output")
    return out if out is not None else json.loads(r["result"])


def call_checked(model, system, user, schema, effort, check, fatal=None) -> dict:
    """call(), then check(data) -> list of errors. One retry with the error list, then Invalid.

    fatal(error) -> bool: when given, only those errors raise after the retry; the rest are printed and
    left for the next stage (the critic fixes or drops an item that breaks a cap).
    """
    data = call(model, system, user, schema, effort)
    errs = check(data)
    if errs:
        print("[llm] output broke rules, retrying once:\n  " + "\n  ".join(errs))
        fix = user + "\n\nYour previous answer broke these rules. Return a corrected answer:\n- " + "\n- ".join(errs)
        data = call(model, system, fix, schema, effort)
        errs = check(data)
        hard = errs if fatal is None else [e for e in errs if fatal(e)]
        if hard:
            raise Invalid("; ".join(hard))
        if errs:
            print("[llm] still broken after the retry, left for the critic:\n  " + "\n  ".join(errs))
    return data


# ---------- caps (PLAN section 3.2) ----------

def words(s):
    return len(s.split())


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def check_question(q, where):
    errs = []
    if not isinstance(q, dict):
        return [f"{where}: question missing"]
    if words(q["text"]) > QUESTION_WORDS:
        errs.append(f"{where}: question text over {QUESTION_WORDS} words")
    if len(q["options"]) not in (3, 4):
        errs.append(f"{where}: needs 3 or 4 options")
    errs += [f"{where}: option '{o}' over {OPTION} words" for o in q["options"] if words(o) > OPTION]
    if not (isinstance(q["correct"], int) and 0 <= q["correct"] < len(q["options"])):
        errs.append(f"{where}: correct index out of range")
    if len(q["explanation"]) > EXPLANATION_CHARS:
        errs.append(f"{where}: explanation over {EXPLANATION_CHARS} characters")
    return errs


def check_item(it, update=False):
    """Caps for one drafted item. update: the item continues a sent story. Returns a list of errors."""
    w = it.get("id", "?")
    errs = []
    if words(it["headline"]) > HEADLINE:
        errs.append(f"{w}: headline over {HEADLINE} words")
    new = it.get("new")
    if update:
        if not (isinstance(new, str) and 0 < words(new) <= NEW):
            errs.append(f"{w}: update item needs 'new', 1-{NEW} words")
        if not REMINDER_MIN <= words(it["summary"]) <= REMINDER:
            errs.append(f"{w}: update reminder (summary) must be {REMINDER_MIN}-{REMINDER} words")
    else:
        if new is not None:
            errs.append(f"{w}: 'new' must be null on an item that is not an update")
        if not SUMMARY_MIN <= words(it["summary"]) <= SUMMARY:
            errs.append(f"{w}: summary must be {SUMMARY_MIN}-{SUMMARY} words")
    if words(it["you"]) > YOU:
        errs.append(f"{w}: 'you' line over {YOU} words")
    if (it.get("attack_id") is None) != (it.get("attack_note") is None):
        errs.append(f"{w}: attack_note and attack_id go together (both set or both null)")
    for k in ("attack_note", "actor"):
        if it.get(k) is not None and words(it[k]) > NOTE:
            errs.append(f"{w}: {k} over {NOTE} words")
    a = it.get("action")
    if a is not None:
        if words(a["text"]) > ACTION:
            errs.append(f"{w}: action over {ACTION} words")
        if a["minutes"] not in (1, 2):
            errs.append(f"{w}: action must take 1 or 2 minutes")
    if it.get("attack_id") is not None and not ATTACK_RE.match(it["attack_id"]):
        errs.append(f"{w}: attack_id must match T1234 or T1234.123, or be null")
    errs += check_question(it["question"], w)
    return errs + check_strings(it, w)


def check_extras(ex, known_terms=(), recent_til=()):
    """Caps for the glossary and Today I Learned. known_terms / recent_til must not be repeated."""
    errs = []
    if len(ex["glossary"]) > GLOSSARY_MAX:
        errs.append(f"glossary: max {GLOSSARY_MAX} terms")
    known = {t.casefold() for t in known_terms}
    for g in ex["glossary"]:
        if words(g["meaning"]) > MEANING:
            errs.append(f"glossary '{g['term']}': meaning over {MEANING} words")
        if g["term"].casefold() in known:
            errs.append(f"glossary '{g['term']}': already defined recently, leave it out")
    t = ex["til"]
    if t is not None:
        if not TIL_MIN <= words(t["text"]) <= TIL:
            errs.append(f"til: text must be {TIL_MIN}-{TIL} words")
        if t["concept"].casefold() in {c.casefold() for c in recent_til}:
            errs.append(f"til: '{t['concept']}' was used in the last {KEEP_TIL} days, pick another")
    return errs + check_strings(ex, "extras")


def check_strings(obj, where):
    return [f"{where}: no links or HTML allowed ('{s[:40]}')"
            for s in strings(obj) if any(f in s for f in FORBIDDEN)]


# ---------- schema pieces ----------

QUESTION = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "correct": {"type": "integer"},
        "explanation": {"type": "string"},
        "topic": {"type": "string"},
    },
    "required": ["text", "options", "correct", "explanation", "topic"],
    "additionalProperties": False,
}
ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "new": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "you": {"type": "string"},
        "action": {"anyOf": [{
            "type": "object",
            "properties": {"text": {"type": "string"}, "minutes": {"type": "integer"}},
            "required": ["text", "minutes"], "additionalProperties": False,
        }, {"type": "null"}]},
        "attack_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "attack_note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "actor": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "question": QUESTION,
    },
    "required": ["id", "headline", "summary", "new", "you", "action", "attack_id", "attack_note", "actor", "question"],
    "additionalProperties": False,
}
EXTRAS = {
    "type": "object",
    "properties": {
        "glossary": {"type": "array", "items": {
            "type": "object",
            "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
            "required": ["term", "meaning"], "additionalProperties": False,
        }},
        "til": {"anyOf": [{
            "type": "object",
            "properties": {"concept": {"type": "string"}, "text": {"type": "string"}},
            "required": ["concept", "text"], "additionalProperties": False,
        }, {"type": "null"}]},
    },
    "required": ["glossary", "til"],
    "additionalProperties": False,
}


# ---------- files ----------

def load(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prompt(name):
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def profile():
    return Path("profile.md").read_text(encoding="utf-8")


def recent_days(n=14, today=None):
    """state.json days from the last n days (T3 owns the file; missing → [])."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cutoff = (today - dt.timedelta(days=n)).isoformat()
    return [d for d in load("data/state.json", {"days": []}).get("days", []) if d.get("date", "") >= cutoff]


def recent_topics(n=14):
    """Quiz topics of the last n days, from every poll."""
    from brief import state
    return sorted({p["question"]["topic"] for d in recent_days(n) for p in state.polls(d)
                   if p.get("question") and p["question"].get("topic")})


def history():
    """(glossary terms, TIL concepts) already taught. state.json first; before its first send, the frozen history.json."""
    s = load("data/state.json", {})
    if "glossary" in s or "til" in s:
        return s.get("glossary", []), s.get("til", [])
    old = load("history.json", {})
    return old.get("glossary", [])[-KEEP_TERMS:], old.get("til", [])[-KEEP_TIL:]


def run(stage, name):
    """Wrap a stage body: any failure → message + exit 1."""
    try:
        stage()
    except Exception as e:  # noqa: BLE001 - every failure stops the run
        print(f"[{name}] FAILED: {type(e).__name__}: {e}")
        return 1
    if spent:
        print(f"[llm] stage tokens: {sum(s[1] for s in spent)} in / {sum(s[2] for s in spent)} out")
    return 0
