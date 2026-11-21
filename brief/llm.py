"""Shared model plumbing for the T2 stages: the one API call, caps, file helpers."""
import datetime as dt
import json
import re
from pathlib import Path

HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
PRICES = {HAIKU: (0.10, 0.50), SONNET: (2.0, 10.0), OPUS: (4.0, 20.0)}  # $ per MTok in/out
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
ATTACK_RE = re.compile(r"^T\d{4}(\.\d{3})?$")
FORBIDDEN = ("http", "www.", "<")

_client = None
spent = []  # (model, in_tokens, out_tokens, dollars) per call, for the stage summary


class Refused(RuntimeError):
    pass


class Invalid(RuntimeError):
    pass


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def call(model, system, user, schema, effort) -> dict:
    """One schema-constrained call. Refusal: Sonnet/Opus fall back server-side, Haiku re-runs on Sonnet."""
    kw = dict(
        model=model, max_tokens=16000, system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if model == HAIKU:
        resp = client().messages.create(**kw)
    else:
        resp = client().beta.messages.create(**kw, betas=[FALLBACK_BETA], fallbacks="default")
    u = resp.usage
    pin, pout = PRICES.get(getattr(resp, "model", model), PRICES.get(model, (0, 0)))
    cost = (u.input_tokens * pin + u.output_tokens * pout) / 1e6
    spent.append((model, u.input_tokens, u.output_tokens, cost))
    print(f"[llm] {model}: {u.input_tokens} in / {u.output_tokens} out tokens (${cost:.4f})")
    if resp.stop_reason == "refusal":
        if model == HAIKU:
            print("[llm] Haiku refused; re-running once on Sonnet")
            return call(SONNET, system, user, schema, effort)
        raise Refused(f"{model} refused ({getattr(resp, 'stop_details', None)})")
    if resp.stop_reason == "max_tokens":
        raise Invalid(f"{model} hit max_tokens")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def call_checked(model, system, user, schema, effort, check) -> dict:
    """call(), then check(data) -> list of errors. One retry with the error list, then Invalid."""
    data = call(model, system, user, schema, effort)
    errs = check(data)
    if errs:
        print("[llm] output broke rules, retrying once:\n  " + "\n  ".join(errs))
        fix = user + "\n\nYour previous answer broke these rules. Return a corrected answer:\n- " + "\n- ".join(errs)
        data = call(model, system, fix, schema, effort)
        errs = check(data)
        if errs:
            raise Invalid("; ".join(errs))
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
    if words(q["text"]) > 30:
        errs.append(f"{where}: question text over 30 words")
    if len(q["options"]) != 3:
        errs.append(f"{where}: needs exactly 3 options")
    errs += [f"{where}: option '{o}' over 6 words" for o in q["options"] if words(o) > 6]
    if not (isinstance(q["correct"], int) and 0 <= q["correct"] < len(q["options"])):
        errs.append(f"{where}: correct index out of range")
    if len(q["explanation"]) > 200:
        errs.append(f"{where}: explanation over 200 characters")
    return errs


def check_item(it):
    """Caps for one drafted item. Returns a list of errors."""
    w = it.get("id", "?")
    errs = []
    if words(it["headline"]) > 10:
        errs.append(f"{w}: headline over 10 words")
    if words(it["you"]) > 12:
        errs.append(f"{w}: 'you' line over 12 words")
    a = it.get("action")
    if a is not None:
        if words(a["text"]) > 14:
            errs.append(f"{w}: action over 14 words")
        if a["minutes"] not in (1, 2):
            errs.append(f"{w}: action must take 1 or 2 minutes")
    if it.get("attack_id") is not None and not ATTACK_RE.match(it["attack_id"]):
        errs.append(f"{w}: attack_id must match T1234 or T1234.123, or be null")
    errs += check_question(it["question"], w)
    return errs + check_strings(it, w)


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
        "you": {"type": "string"},
        "action": {"anyOf": [{
            "type": "object",
            "properties": {"text": {"type": "string"}, "minutes": {"type": "integer"}},
            "required": ["text", "minutes"], "additionalProperties": False,
        }, {"type": "null"}]},
        "attack_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "question": QUESTION,
    },
    "required": ["id", "headline", "you", "action", "attack_id", "question"],
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


def run(stage, name):
    """Wrap a stage body: any failure → message + exit 1."""
    try:
        stage()
    except Exception as e:  # noqa: BLE001 - every failure stops the run
        print(f"[{name}] FAILED: {type(e).__name__}: {e}")
        return 1
    total = sum(s[3] for s in spent)
    if spent:
        print(f"[llm] stage cost ${total:.4f}")
    return 0
