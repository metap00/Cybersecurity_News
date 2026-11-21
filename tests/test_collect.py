import json
from datetime import datetime, timezone
from pathlib import Path

from brief import collect

FIX = Path(__file__).parent / "fixtures" / "collect"
NOW = datetime(2026, 11, 21, 5, 17, tzinfo=timezone.utc)


def raw(title, url, text="", feed="F", hour=1, tier=2):
    r = {"title": title, "url": url, "text": text,
         "published": datetime(2026, 11, 21, hour, tzinfo=timezone.utc)}
    return collect.make_candidate(r, feed, tier)


def test_rss_parsing():
    items = collect.parse_feed((FIX / "rss.xml").read_bytes())
    assert len(items) == 2
    it = items[0]
    assert it["title"].startswith("Google issues")
    assert it["published"] == datetime(2026, 11, 20, 9, 12, tzinfo=timezone.utc)
    # full content preferred, HTML stripped, script dropped, whitespace collapsed
    assert it["text"] == "Google patched CVE-2026-12345 in Chrome. Update now & relaunch."


def test_atom_parsing():
    [it] = collect.parse_feed((FIX / "atom.xml").read_bytes())
    assert it["url"] == "https://Atom.Example.org/ransomware/"  # rel=alternate wins
    assert it["published"] == datetime(2026, 11, 21, 1, 30, tzinfo=timezone.utc)
    assert it["text"] == "A ransomware gang encrypted systems at a hospital chain."


def test_summary_cut_and_keys():
    c = raw("t", "https://Ex.com/a/b/?q=1#frag", text="CVE-2026-9999 " + "x" * 5000 + " CVE-2026-8888")
    assert len(c["summary"]) == 1200
    assert c["cves"] == ["CVE-2026-9999"]  # a CVE after character 1,200 is not a key
    assert c["keys"] == ["cve-2026-9999", "u:ex.com/a/b"]


def test_tier_read_from_opml_default_2(tmp_path):
    opml = tmp_path / "f.opml"
    opml.write_text('<opml><body><outline title="A" tier="1" xmlUrl="https://a.test/"/>'
                    '<outline text="B" xmlUrl="https://b.test/"/></body></opml>', encoding="utf-8")
    assert collect.load_feeds(opml) == [("A", "https://a.test/", 1), ("B", "https://b.test/", 2)]


def test_merge_cites_lowest_tier_then_longest_text():
    a = raw("Big vCenter flaw exploited", "https://a.com/1", text="aggregator rewrite, quite long", feed="A", tier=3)
    b = raw("Big vCenter flaw exploited!", "https://b.com/2", text="news", feed="B", tier=2)
    c = raw("Big vCenter flaw exploited.", "https://c.com/3", text="lab report", feed="C", tier=1)
    [m] = collect.merge([a, b, c])
    assert (m["feed"], m["tier"], m["also"]) == ("C", 1, ["A", "B"])
    assert [(s["feed"], s["summary"]) for s in m["sources"]] == [
        ("A", "aggregator rewrite, quite long"), ("B", "news")]  # longest first
    d = raw("Same tier story", "https://d.com/4", text="short", feed="D")
    e = raw("Same tier story", "https://e.com/5", text="longer text", feed="E")
    [m] = collect.merge([d, e])
    assert m["feed"] == "E" and m["sources"][0]["feed"] == "D"
    [alone] = collect.merge([d])
    assert alone["sources"] == []


def test_kev_candidates():
    vulns = json.loads((FIX / "kev.json").read_text(encoding="utf-8"))["vulnerabilities"]
    one, three = collect.kev_candidates(vulns, datetime(2026, 11, 20, 5, 17, tzinfo=timezone.utc))
    assert one["title"] == "CISA KEV adds an exploited flaw in Fortinet FortiOS"
    assert one["url"] == "https://www.cisa.gov/known-exploited-vulnerabilities-catalog?field_cve=CVE-2026-22222"
    assert one["keys"] == ["cve-2026-22222", "kev:2026-11-20"]
    assert (one["feed"], one["tier"]) == ("CISA KEV", 1)
    assert one["summary"] == ("Fortinet FortiOS (CVE-2026-22222): Fortinet FortiOS contains a path traversal "
                              "vulnerability. Ransomware use: Known. US federal deadline: 2026-12-11.")
    assert three["title"] == ("CISA KEV adds 3 exploited flaws: Google Chromium V8, VMware vCenter Server, PHP PHP")
    assert three["url"] == "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
    assert "kev:2026-11-21" in three["keys"] and not any(k.startswith("u:") for k in three["keys"])
    assert all("CVE-2026-11111" not in c["cves"] for c in (one, three))  # dated before since


def test_fetch_third_attempt_after_two_failures(monkeypatch):
    calls = []

    def fail_then_ok(url, cap):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("403")
        return b"ok"

    monkeypatch.setattr(collect, "_urllib_get", fail_then_ok)
    monkeypatch.setattr(collect, "_curl_get", fail_then_ok)
    monkeypatch.setattr(collect.time, "sleep", lambda s: calls.append(f"sleep {s}"))
    assert collect.fetch("https://x.test/") == b"ok"
    assert calls == ["https://x.test/", "https://x.test/", "sleep 3", "https://x.test/"]


def test_window():
    assert collect.window_start({"days": []}, NOW) == datetime(2026, 11, 20, 5, 17, tzinfo=timezone.utc)
    state = {"days": [
        {"date": "2026-11-20", "mode": "full", "sent_at": "2026-11-20T05:21:04Z"},
        {"date": "2026-11-20", "mode": "weekly", "sent_at": "2026-11-20T18:00:00Z"},
    ]}
    assert collect.window_start(state, NOW) == datetime(2026, 11, 20, 5, 21, 4, tzinfo=timezone.utc)
    old = {"days": [{"date": "2026-11-10", "mode": "full", "sent_at": "2026-11-10T05:00:00Z"}]}
    assert collect.window_start(old, NOW) == datetime(2026, 11, 18, 5, 17, tzinfo=timezone.utc)


def test_merge_same_url():
    a = raw("Alpha story", "https://x.com/a?utm=1", text="short", feed="A")
    b = raw("Totally different words", "https://X.com/a/", text="much longer text", feed="B")
    [m] = collect.merge([a, b])
    assert m["feed"] == "B" and m["also"] == ["A"]


def test_merge_shared_cve():
    a = raw("Chrome bug CVE-2026-1111", "https://a.com/1", feed="A", text="longest summary here")
    b = raw("Patch now", "https://b.com/2", text="CVE-2026-1111", feed="B")
    [m] = collect.merge([a, b])
    assert m["feed"] == "A" and m["also"] == ["B"]
    assert set(m["keys"]) == {"cve-2026-1111", "u:a.com/1", "u:b.com/2"}


def test_merge_similar_title():
    a = raw("Microsoft patches 60 flaws in November update", "https://a.com/1", feed="A")
    b = raw("Microsoft patches 61 flaws in November update", "https://b.com/2", feed="B", text="x")
    c = raw("Unrelated phishing kit spotted", "https://c.com/3", feed="C")
    assert len(collect.merge([a, b, c])) == 2


def setup_run(tmp_path, monkeypatch, feeds, state=None, kev_fails=False,
              kev=b'{"vulnerabilities": [{"cveID": "CVE-2026-12345"}]}'):
    opml = tmp_path / "feeds.opml"
    opml.write_text("<opml><body>" + "".join(
        f'<outline title="{n}" xmlUrl="https://{n}.test/feed"/>' for n in feeds) + "</body></opml>",
        encoding="utf-8")
    st = tmp_path / "state.json"
    if state:
        st.write_text(json.dumps(state), encoding="utf-8")
    bodies = {"rss": (FIX / "rss.xml").read_bytes(), "atom": (FIX / "atom.xml").read_bytes(),
              "rss2": (FIX / "rss.xml").read_bytes()}

    def fake_fetch(url, cap=collect.FEED_CAP):
        if url == collect.KEV_URL:
            if kev_fails:
                raise OSError("down")
            return kev
        name = url.split("//")[1].split(".")[0]
        if name not in bodies:
            raise OSError("HTTP Error 404")
        return bodies[name]

    monkeypatch.setattr(collect, "fetch", fake_fetch)
    monkeypatch.setattr(collect, "_now", lambda: NOW)
    monkeypatch.setattr(collect, "MIN_FEEDS_OK", 3)  # the fixtures have 4-5 sources, not 18
    out = tmp_path / "out" / "candidates.json"
    return ["--opml", str(opml), "--state", str(st), "--out", str(out)], out


def test_run_dead_feed_does_not_stop(tmp_path, monkeypatch, capsys):
    argv, out = setup_run(tmp_path, monkeypatch, ["rss", "atom", "rss2", "dead"])
    assert collect.main(argv) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    dead = [f for f in doc["feeds"] if f["name"] == "dead"][0]
    assert dead["ok"] is False and "404" in dead["error"]
    assert [c["id"] for c in doc["candidates"]] == ["c01", "c02"]  # rss+rss2 merged, old item dropped
    first, second = doc["candidates"]
    assert first["title"].startswith("Ransomware")  # newest first
    assert second["kev"] is True and second["also"] == ["rss2"]
    assert second["published"] == "2026-11-20T09:12:00Z"
    assert doc["since"] == "2026-11-20T05:17:00Z"
    assert "dead" in capsys.readouterr().out


def test_run_kev_candidate_never_merges(tmp_path, monkeypatch):
    argv, out = setup_run(tmp_path, monkeypatch, ["rss", "atom", "rss2"],
                          kev=(FIX / "kev.json").read_bytes())
    assert collect.main(argv) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    kev = [c for c in doc["candidates"] if c["feed"] == "CISA KEV"]
    chrome = [c for c in doc["candidates"] if c["title"].startswith("Google issues")]
    assert len(kev) == 2 and len(chrome) == 1  # both carry CVE-2026-12345, still apart
    assert chrome[0]["kev"] is True and chrome[0]["tier"] == 2 and chrome[0]["sources"][0]["feed"] == "rss2"
    assert doc["feeds"][-1] == {"name": "CISA KEV", "ok": True, "items": 4, "error": None}


def test_run_fewer_than_min_sources(tmp_path, monkeypatch):
    argv, out = setup_run(tmp_path, monkeypatch, ["rss", "atom", "dead", "gone"], kev_fails=True)
    assert collect.main(argv) == 1
    assert not out.exists()


def test_run_14_day_drop_and_kev_failure(tmp_path, monkeypatch):
    state = {"version": 1, "days": [
        {"date": "2026-11-15", "mode": "full", "sent_at": "2026-11-15T05:20:00Z",
         "keys": ["cve-2026-12345"]},
        {"date": "2026-11-01", "mode": "full", "sent_at": "2026-11-01T05:20:00Z",
         "keys": ["u:atom.example.org/ransomware"]},  # older than 14 days: ignored
    ]}
    argv, out = setup_run(tmp_path, monkeypatch, ["rss", "atom", "rss2"], state, kev_fails=True)
    assert collect.main(argv) == 0
    [only] = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert only["title"].startswith("Ransomware") and only["kev"] is False


def test_quiet_day_exits_0(tmp_path, monkeypatch):
    state = {"days": [{"date": "2026-11-21", "mode": "full", "sent_at": "2026-11-21T05:00:00Z"}]}
    argv, out = setup_run(tmp_path, monkeypatch, ["rss", "atom", "rss2"], state)
    assert collect.main(argv) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["candidates"] == []
