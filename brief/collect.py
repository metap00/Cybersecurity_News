"""Stage 1: fetch feeds + CISA KEV, write out/candidates.json. No model.

python -m brief.collect [--opml feeds.opml] [--state data/state.json] [--out out/candidates.json]
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
KEV_URL = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
TIMEOUT = 15
FEED_CAP = 3 * 1024 * 1024
KEV_CAP = 30 * 1024 * 1024
SUMMARY_MAX = 1200
MIN_FEEDS_OK = 3
SIMILAR = 0.85
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)


def _now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _urllib_get(url, cap):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(cap + 1)


def _curl_get(url, cap):
    # Some CDNs (CISA's Akamai) 403 Python's TLS fingerprint but accept curl's.
    r = subprocess.run(["curl", "-sSfL", "--max-time", str(TIMEOUT), "-A", UA, url],
                       capture_output=True, timeout=TIMEOUT + 5)
    if r.returncode:
        raise OSError(r.stderr.decode(errors="replace").strip() or f"curl exit {r.returncode}")
    return r.stdout[:cap + 1]


def fetch(url, cap=FEED_CAP):
    """GET with a browser UA, 15 s timeout, size cap, one retry (via curl when installed)."""
    retry = _curl_get if shutil.which("curl") else _urllib_get
    try:
        data = _urllib_get(url, cap)
    except Exception:
        data = retry(url, cap)
    if len(data) > cap:
        raise ValueError(f"larger than {cap} bytes")
    return data


def load_feeds(opml_path):
    root = ET.parse(opml_path).getroot()
    return [(o.get("title") or o.get("text") or o.get("xmlUrl"), o.get("xmlUrl"))
            for o in root.iter("outline") if o.get("xmlUrl")]


# --- parsing ---------------------------------------------------------------

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(html):
    p = _Text()
    p.feed(html or "")
    p.close()
    return " ".join("".join(p.parts).split())


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el, *names):
    """First child whose local tag is in names (checked in the given order)."""
    for name in names:
        for c in el:
            if _local(c.tag) == name:
                return c
    return None


def _text(el, *names):
    c = _child(el, *names)
    return (c.text or "").strip() if c is not None else ""


def _date(s):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.strip())
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _atom_link(entry):
    links = [c for c in entry if _local(c.tag) == "link"]
    for c in links:
        if c.get("rel") in (None, "alternate"):
            return c.get("href", "")
    return links[0].get("href", "") if links else ""


def parse_feed(data):
    """RSS 2.0 items and Atom entries -> [{title, url, published, text}]."""
    out = []
    for el in ET.fromstring(data).iter():
        kind = _local(el.tag)
        if kind == "item":
            url = _text(el, "link") or _text(el, "guid")
            published = _date(_text(el, "pubDate", "date"))
            body = _text(el, "encoded") or _text(el, "description")
        elif kind == "entry":
            url = _atom_link(el)
            published = _date(_text(el, "published", "updated"))
            body = _text(el, "content") or _text(el, "summary")
        else:
            continue
        title = plain(_text(el, "title"))
        if title and url and published:
            out.append({"title": title, "url": url.strip(), "published": published,
                        "text": plain(body)})
    return out


# --- keys and merging ------------------------------------------------------

def canon(url):
    p = urlsplit(url.strip())
    return f"{p.netloc.lower()}{p.path.rstrip('/')}"


def make_candidate(raw, feed):
    cves = sorted({c.upper() for c in CVE_RE.findall(raw["title"] + " " + raw["text"])})
    return {
        "title": raw["title"], "url": raw["url"], "feed": feed,
        "published": raw["published"], "summary": raw["text"][:SUMMARY_MAX],
        "cves": cves, "kev": False, "also": [],
        "keys": [c.lower() for c in cves] + [f"u:{canon(raw['url'])}"],
    }


def _same(a, b):
    if set(a["keys"]) & set(b["keys"]):  # same canonical URL or a shared CVE
        return True
    ratio = difflib.SequenceMatcher(None, a["title"].lower(), b["title"].lower()).ratio()
    return ratio >= SIMILAR


def merge(items):
    """Group duplicates; keep the longest summary, list other feeds in `also`."""
    groups = []
    for it in items:
        hits = [g for g in groups if any(_same(it, m) for m in g)]
        merged = [m for g in hits for m in g] + [it]  # feed order: ties go to the earlier feed
        groups = [g for g in groups if g not in hits] + [merged]
    out = []
    for g in groups:
        best = max(g, key=lambda m: len(m["summary"]))
        c = dict(best)
        c["cves"] = sorted({x for m in g for x in m["cves"]})
        c["keys"] = list(dict.fromkeys(k for m in [best] + g for k in m["keys"]))
        c["also"] = list(dict.fromkeys(m["feed"] for m in g if m["feed"] != best["feed"]))
        out.append(c)
    return out


# --- state -----------------------------------------------------------------

def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"version": 1, "days": []}


def window_start(state, now):
    since = now - timedelta(hours=24)
    for day in reversed(state.get("days", [])):
        if day.get("mode") != "weekly":
            if day.get("sent_at"):
                since = _date(day["sent_at"]) or since
            break
    return max(since, now - timedelta(hours=72))


def recent_keys(state, now, days=14):
    cutoff = (now - timedelta(days=days)).date().isoformat()
    return {k for d in state.get("days", []) if d.get("date", "") >= cutoff
            for k in d.get("keys", [])}


def kev_set():
    data = json.loads(fetch(KEV_URL, cap=KEV_CAP))
    return {v["cveID"].upper() for v in data["vulnerabilities"]}


# --- main ------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m brief.collect")
    ap.add_argument("--opml", default="feeds.opml")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--out", default="out/candidates.json")
    args = ap.parse_args(argv)

    now = _now()
    state = load_state(args.state)
    since = window_start(state, now)

    health, raw = [], []
    for name, url in load_feeds(args.opml):
        try:
            items = [i for i in parse_feed(fetch(url)) if i["published"] >= since]
            raw += [make_candidate(i, name) for i in items]
            health.append({"name": name, "ok": True, "items": len(items), "error": None})
        except Exception as e:
            health.append({"name": name, "ok": False, "items": 0,
                           "error": f"{type(e).__name__}: {e}"[:200]})

    print(f"{'feed':<32} {'ok':<4} {'items':>5}  error")
    for h in health:
        print(f"{h['name'][:32]:<32} {'yes' if h['ok'] else 'NO':<4} {h['items']:>5}  {h['error'] or ''}")
    ok = sum(h["ok"] for h in health)
    print(f"{ok}/{len(health)} feeds ok, since {iso(since)}")
    if ok < MIN_FEEDS_OK:
        print(f"error: fewer than {MIN_FEEDS_OK} feeds answered", file=sys.stderr)
        return 1

    seen = recent_keys(state, now)
    cands = [c for c in merge(raw) if not seen & set(c["keys"])]

    try:
        kev = kev_set()
    except Exception as e:
        print(f"warning: KEV fetch failed ({type(e).__name__}); kev=false", file=sys.stderr)
        kev = set()

    cands.sort(key=lambda c: c["published"], reverse=True)
    out = []
    for n, c in enumerate(cands, 1):
        out.append({"id": f"c{n:02d}", "title": c["title"], "url": c["url"], "feed": c["feed"],
                    "published": iso(c["published"]), "summary": c["summary"],
                    "cves": c["cves"], "kev": any(x in kev for x in c["cves"]),
                    "also": c["also"], "keys": c["keys"]})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"generated_at": iso(now), "since": iso(since), "feeds": health,
                   "candidates": out}, f, ensure_ascii=False, indent=2)
    print(f"{len(out)} candidates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
