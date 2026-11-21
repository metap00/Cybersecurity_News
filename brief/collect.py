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
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

# No browser version to go stale: Cloudflare challenged the old Chrome/131 string.
UA = "Mozilla/5.0 (compatible; rss-reader/1.0)"
KEV_URL = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
KEV_FEED = "CISA KEV"
KEV_PAGE = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
TIMEOUT = 15
FEED_CAP = 8 * 1024 * 1024
KEV_CAP = 30 * 1024 * 1024
SUMMARY_MAX = 1200
MIN_FEEDS_OK = 6  # of 18 sources: the same share as 3 of 10 before
RETRY_WAIT = 3
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
    """GET with a reader UA, 15 s timeout, size cap. 3 attempts: Python, curl, curl again
    after 3 s (Microsoft's burst limit). Without curl, Python each time."""
    retry = _curl_get if shutil.which("curl") else _urllib_get
    try:
        data = _urllib_get(url, cap)
    except Exception:
        try:
            data = retry(url, cap)
        except Exception:
            time.sleep(RETRY_WAIT)
            data = retry(url, cap)
    if len(data) > cap:
        raise ValueError(f"larger than {cap} bytes")
    return data


def load_feeds(opml_path):
    """[(name, url, tier)]; a missing tier is 2."""
    root = ET.parse(opml_path).getroot()
    return [(o.get("title") or o.get("text") or o.get("xmlUrl"), o.get("xmlUrl"), int(o.get("tier") or 2))
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


def make_candidate(raw, feed, tier=2):
    summary = raw["text"][:SUMMARY_MAX]  # CVE keys come from the text the models see
    cves = sorted({c.upper() for c in CVE_RE.findall(raw["title"] + " " + summary)})
    return {
        "title": raw["title"], "url": raw["url"], "feed": feed, "tier": tier,
        "published": raw["published"], "summary": summary,
        "cves": cves, "kev": False, "also": [],
        "keys": [c.lower() for c in cves] + [f"u:{canon(raw['url'])}"],
    }


def _same(a, b):
    if set(a["keys"]) & set(b["keys"]):  # same canonical URL or a shared CVE
        return True
    ratio = difflib.SequenceMatcher(None, a["title"].lower(), b["title"].lower()).ratio()
    return ratio >= SIMILAR


def merge(items):
    """Group duplicates; cite the lowest tier, then the longest summary. The other members
    go in `also` (feed names) and `sources` (their text, longest first, max 3)."""
    groups = []
    for it in items:
        hits = [g for g in groups if any(_same(it, m) for m in g)]
        merged = [m for g in hits for m in g] + [it]  # feed order: ties go to the earlier feed
        groups = [g for g in groups if g not in hits] + [merged]
    out = []
    for g in groups:
        best = min(g, key=lambda m: (m["tier"], -len(m["summary"])))
        c = dict(best)
        rest = sorted((m for m in g if m is not best), key=lambda m: -len(m["summary"]))
        c["sources"] = [{k: m[k] for k in ("feed", "tier", "title", "summary")} for m in rest[:3]]
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


def kev_candidates(vulns, since):
    """One candidate per KEV dateAdded on or after since's date. Built by code, no model."""
    days = {}
    for v in vulns:
        if v.get("dateAdded", "") >= since.date().isoformat():
            days.setdefault(v["dateAdded"], []).append(v)
    out = []
    for day, vs in sorted(days.items()):
        names = [f"{v['vendorProject']} {v['product']}" for v in vs]
        if len(vs) == 1:
            title = f"CISA KEV adds an exploited flaw in {names[0]}"
            url = f"{KEV_PAGE}?field_cve={vs[0]['cveID']}"
        else:
            title = f"CISA KEV adds {len(vs)} exploited flaws: {', '.join(names)}"
            url = KEV_PAGE
        summary = " ".join(
            f"{n} ({v['cveID']}): {v.get('shortDescription', '').strip()} "
            f"Ransomware use: {v.get('knownRansomwareCampaignUse', 'Unknown')}. "
            f"US federal deadline: {v.get('dueDate', '')}." for n, v in zip(names, vs))
        cves = sorted({v["cveID"].upper() for v in vs})
        out.append({"title": title, "url": url, "feed": KEV_FEED, "tier": 1,
                    "published": datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                    "summary": summary[:SUMMARY_MAX], "cves": cves, "also": [], "sources": [],
                    # no u: key: the catalog URL is the same every day and would block later batches
                    "keys": [c.lower() for c in cves] + [f"kev:{day}"]})
    return out


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

    def err(e):
        return f"{type(e).__name__}: {e}"[:200]

    health, raw = [], []
    for name, url, tier in load_feeds(args.opml):
        try:
            items = [i for i in parse_feed(fetch(url)) if i["published"] >= since]
            raw += [make_candidate(i, name, tier) for i in items]
            health.append({"name": name, "ok": True, "items": len(items), "error": None})
        except Exception as e:
            health.append({"name": name, "ok": False, "items": 0, "error": err(e)})

    # One download for both the KEV candidates and the kev flag.
    try:
        vulns = json.loads(fetch(KEV_URL, cap=KEV_CAP))["vulnerabilities"]
        kev = {v["cveID"].upper() for v in vulns}
        kev_cands = kev_candidates(vulns, since)
        health.append({"name": KEV_FEED, "ok": True, "error": None,
                       "items": sum(len(c["cves"]) for c in kev_cands)})
    except Exception as e:
        print(f"warning: KEV fetch failed ({type(e).__name__}); kev=false", file=sys.stderr)
        kev, kev_cands = set(), []
        health.append({"name": KEV_FEED, "ok": False, "items": 0, "error": err(e)})

    print(f"{'feed':<32} {'ok':<4} {'items':>5}  error")
    for h in health:
        print(f"{h['name'][:32]:<32} {'yes' if h['ok'] else 'NO':<4} {h['items']:>5}  {h['error'] or ''}")
    ok = sum(h["ok"] for h in health)
    print(f"{ok}/{len(health)} sources ok, since {iso(since)}")
    if ok < MIN_FEEDS_OK:
        print(f"error: fewer than {MIN_FEEDS_OK} sources answered", file=sys.stderr)
        return 1

    seen = recent_keys(state, now)
    # KEV batches join after merge: a shared CVE must not pull unrelated flaws into one story.
    cands = [c for c in merge(raw) + kev_cands if not seen & set(c["keys"])]

    cands.sort(key=lambda c: c["published"], reverse=True)
    out = []
    for n, c in enumerate(cands, 1):
        out.append({"id": f"c{n:02d}", "title": c["title"], "url": c["url"], "feed": c["feed"],
                    "tier": c["tier"], "published": iso(c["published"]), "summary": c["summary"],
                    "cves": c["cves"], "kev": any(x in kev for x in c["cves"]),
                    "also": c["also"], "sources": c["sources"], "keys": c["keys"]})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"generated_at": iso(now), "since": iso(since), "feeds": health,
                   "candidates": out}, f, ensure_ascii=False, indent=2)
    print(f"{len(out)} candidates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
