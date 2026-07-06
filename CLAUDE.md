# Cybersecurity News Agent

You run daily to produce a cybersecurity news digest from the last 24 hours.

## Workflow

**1. Parse `feeds.opml`** — extract all `xmlUrl` values and feed names.

**2. Fetch each RSS feed** via WebFetch. Collect articles from the last 24 hours. Skip feeds that fail.

**3. Score each article:**
- **CRITICAL** `#dc2626` — active zero-days, live ransomware, major breaches (millions affected), nation-state attacks
- **HIGH** `#ea580c` — CVEs with CVSS 7.0+, significant breaches, new malware, critical patch advisories
- **MEDIUM** `#ca8a04` — lower-severity CVEs, phishing campaigns, security tool updates
- **LOW** `#6b7280` — vendor news, opinions, conferences

**4. Fetch full content** for all CRITICAL and HIGH articles via WebFetch (max 7 total). Deduplicate cross-feed stories.

**5. For each CRITICAL/HIGH/MEDIUM story identify:**
- **MITRE ATT&CK** — most relevant tactic + technique ID and name. One sentence explaining how it applies to THIS specific story.
- **Threat actor** — if a named APT group or gang is mentioned, prepare: who they are, nation-state or criminal, who they target, what they're known for.

**6. Determine threat level + read time:**
- 🔴 ELEVATED `#dc2626` — any CRITICAL
- 🟠 ACTIVE `#ea580c` — 2+ HIGH, no CRITICAL
- 🟡 MODERATE `#ca8a04` — 1 HIGH or mostly MEDIUM
- 🟢 QUIET `#16a34a` — nothing significant
- Read time: count visible words ÷ 200, round up → `~X min read`

**7. Check `history.json`** from repo root if it exists:
```json
{
  "til": ["last 7 TIL concept names"],
  "glossary": ["last 50 terms defined"],
  "week": {
    "critical": 0, "high": 0, "medium": 0,
    "techniques": [], "actors": []
  }
}
```
Do NOT repeat any TIL concept or glossary term. If file doesn't exist, start fresh.

**8. If today is Sunday** — prepare a "Week in Review" section from `week` data in history.json: total stories by severity, ATT&CK techniques seen, threat actors, 2-sentence week summary.

**9. Pick "Today I Learned"** — one fresh concept, 3 sentences in plain English.

**10. Build glossary** — every new acronym/jargon term used today, one-sentence definition each.

**11. Write the FULL interactive digest** to `summaries/YYYY-MM-DD.html` using the Full HTML Template below.

**12. Write the COMPACT email digest** to `summaries/YYYY-MM-DD-email.html` using the Email HTML Template below.

**13. Update `history.json`:**
- Add today's TIL to `til` (keep last 7)
- Add today's glossary terms to `glossary` (keep last 50)
- Increment `week.critical/high/medium` with today's counts
- Add today's ATT&CK IDs to `week.techniques` (no duplicates)
- Add today's threat actors to `week.actors` (no duplicates)
- If today is Sunday, reset all `week` fields after generating the recap

**14. Commit and push** using the GitHub PAT from your session prompt:
```bash
git remote set-url origin https://YOUR_PAT@github.com/metap00/Cybersecurity_News.git
git config user.email "noreply@anthropic.com"
git config user.name "Cybersecurity News Agent"
git add summaries/ history.json
git commit -m "Daily digest: $(date +%Y-%m-%d)"
git push origin HEAD:main
```

---

## Full HTML Template (for GitHub Pages — `summaries/YYYY-MM-DD.html`)

Use **inline styles only**. `<details>/<summary>` works here in the browser.

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Cybersecurity News — DATE</title></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;background:#f3f4f6;padding:16px;">

<!-- THREAT BANNER -->
<div style="background:THREAT_COLOR;color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.85;">EMOJI THREAT_LEVEL</div>
  <div style="font-size:20px;font-weight:bold;margin-top:4px;">Cybersecurity News — DATE</div>
  <div style="font-size:13px;opacity:.85;margin-top:4px;">N stories · N critical · N high · N medium · ~X min read</div>
</div>

<!-- STORY CARD -->
<div style="background:white;border-left:4px solid SEVERITY_COLOR;border-radius:4px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="margin-bottom:8px;">
    <span style="background:SEVERITY_COLOR;color:white;font-size:11px;font-weight:bold;padding:2px 8px;border-radius:3px;">SEVERITY</span>
    <span style="font-size:12px;color:#6b7280;margin-left:8px;">SOURCE · X hours ago</span>
  </div>
  <details>
    <summary style="font-size:15px;font-weight:bold;color:#111827;cursor:pointer;list-style:none;">TITLE</summary>
    <div style="margin-top:10px;font-size:13px;color:#374151;line-height:1.6;">
      <div>🔍 <strong>What happened:</strong> ONE_SENTENCE</div>
      <div style="margin-top:3px;">👤 <strong>Who's affected:</strong> ONE_SENTENCE</div>
      <div style="margin-top:3px;">✅ <strong>What to do:</strong> ONE_SENTENCE</div>
    </div>
    <div style="margin-top:10px;padding:8px 10px;background:#faf5ff;border-left:3px solid #7c3aed;border-radius:3px;font-size:12px;color:#374151;">
      🎯 <strong style="color:#6d28d9;">ATT&CK:</strong> [TACTIC] TID · TECHNIQUE_NAME<br>
      <span style="color:#6b7280;">HOW_IT_APPLIES_TO_THIS_STORY</span>
    </div>
    <details style="margin-top:10px;">
      <summary style="font-size:13px;color:#4f46e5;cursor:pointer;font-weight:500;">▶ Full analysis &amp; beginner explanation</summary>
      <div style="margin-top:10px;padding:12px;background:#f8fafc;border-radius:4px;font-size:13px;color:#374151;line-height:1.6;">
        FULL_ANALYSIS_2_TO_4_PARAGRAPHS
        <div style="margin-top:10px;padding:10px;background:#eff6ff;border-radius:4px;border-left:3px solid #3b82f6;">
          <strong style="color:#1d4ed8;">🎓 For beginners:</strong> PLAIN_ENGLISH_EXPLANATION
        </div>
        <div style="margin-top:8px;font-size:12px;color:#6b7280;">CVE-ID · CVSS: X.X/10 — ONE_SENTENCE_SCORE_EXPLANATION</div>
      </div>
    </details>
  </details>
</div>

<!-- THREAT ACTOR CARD (only when named APT/group mentioned) -->
<div style="background:#1e1b4b;color:white;border-radius:4px;padding:12px 16px;margin-top:-6px;margin-bottom:10px;font-size:13px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.7;margin-bottom:6px;">⚠ Threat Actor</div>
  <div style="font-weight:bold;font-size:15px;">ACTOR_NAME</div>
  <div style="opacity:.85;margin-top:4px;">TYPE · Attributed to: COUNTRY</div>
  <div style="margin-top:8px;">🎯 <strong>Targets:</strong> WHO_THEY_TARGET</div>
  <div style="margin-top:3px;">🔧 <strong>Known for:</strong> WHAT_THEY_DO</div>
</div>

<!-- TODAY I LEARNED -->
<details style="background:white;border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <summary style="font-size:15px;font-weight:bold;color:#111827;cursor:pointer;">💡 Today I Learned: CONCEPT_NAME ▶</summary>
  <div style="margin-top:10px;padding:12px;background:#f0fdf4;border-radius:4px;font-size:13px;color:#374151;line-height:1.6;">
    THREE_SENTENCE_EXPLANATION
  </div>
</details>

<!-- GLOSSARY -->
<details style="background:white;border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <summary style="font-size:15px;font-weight:bold;color:#111827;cursor:pointer;">📖 Glossary: TERM · TERM · TERM ▶</summary>
  <div style="margin-top:10px;">
    <div style="padding:7px 0;border-bottom:1px solid #f3f4f6;font-size:13px;">
      <strong style="color:#111827;">TERM</strong> — DEFINITION
    </div>
  </div>
</details>

<!-- WEEK IN REVIEW (Sundays only) -->
<div style="background:white;border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="font-size:15px;font-weight:bold;color:#111827;margin-bottom:12px;">📅 Week in Review</div>
  <div style="display:flex;gap:10px;margin-bottom:12px;">
    <div style="flex:1;text-align:center;padding:10px;background:#fef2f2;border-radius:6px;">
      <div style="font-size:22px;font-weight:bold;color:#dc2626;">N</div>
      <div style="font-size:11px;color:#6b7280;">Critical</div>
    </div>
    <div style="flex:1;text-align:center;padding:10px;background:#fff7ed;border-radius:6px;">
      <div style="font-size:22px;font-weight:bold;color:#ea580c;">N</div>
      <div style="font-size:11px;color:#6b7280;">High</div>
    </div>
    <div style="flex:1;text-align:center;padding:10px;background:#fefce8;border-radius:6px;">
      <div style="font-size:22px;font-weight:bold;color:#ca8a04;">N</div>
      <div style="font-size:11px;color:#6b7280;">Medium</div>
    </div>
  </div>
  <div style="font-size:13px;color:#374151;margin-bottom:6px;"><strong>ATT&CK this week:</strong> T1190 · T1566</div>
  <div style="font-size:13px;color:#374151;margin-bottom:10px;"><strong>Threat actors:</strong> Lazarus Group</div>
  <div style="font-size:13px;color:#374151;line-height:1.6;padding:10px;background:#f8fafc;border-radius:4px;">TWO_SENTENCE_WEEK_SUMMARY</div>
</div>

<!-- ALSO TODAY -->
<div style="background:white;border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="font-size:15px;font-weight:bold;color:#111827;margin-bottom:10px;">Also Today</div>
  <div style="padding:6px 0;border-bottom:1px solid #f3f4f6;font-size:13px;">
    <span style="background:SEVERITY_COLOR;color:white;font-size:10px;font-weight:bold;padding:1px 6px;border-radius:2px;margin-right:6px;">SEVERITY</span>
    <a href="URL" style="color:#374151;text-decoration:none;">TITLE</a>
    <span style="color:#9ca3af;font-size:11px;"> · SOURCE</span>
  </div>
</div>

<!-- FOOTER -->
<div style="text-align:center;font-size:11px;color:#9ca3af;padding:16px 0;">
  Generated by Claude · 10 feeds monitored · DATE
</div>

</body>
</html>
```

---

## Email HTML Template (compact teaser — `summaries/YYYY-MM-DD-email.html`)

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;background:#f3f4f6;padding:16px;">

<!-- BANNER -->
<div style="background:THREAT_COLOR;color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.85;">EMOJI THREAT_LEVEL</div>
  <div style="font-size:20px;font-weight:bold;margin-top:4px;">Cybersecurity News — DATE</div>
  <div style="font-size:13px;opacity:.85;margin-top:4px;">N stories · N critical · N high · ~X min read</div>
  <a href="https://metap00.github.io/Cybersecurity_News/summaries/YYYY-MM-DD.html" style="display:inline-block;margin-top:12px;background:rgba(255,255,255,.2);color:white;padding:6px 14px;border-radius:4px;font-size:13px;text-decoration:none;font-weight:500;">Open Full Interactive Digest →</a>
</div>

<!-- COMPACT STORY CARD (no collapsible — just teaser) -->
<div style="background:white;border-left:4px solid SEVERITY_COLOR;border-radius:4px;padding:12px 16px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="margin-bottom:6px;">
    <span style="background:SEVERITY_COLOR;color:white;font-size:11px;font-weight:bold;padding:2px 8px;border-radius:3px;">SEVERITY</span>
    <span style="font-size:12px;color:#6b7280;margin-left:8px;">SOURCE</span>
  </div>
  <a href="ARTICLE_URL" style="font-size:14px;font-weight:bold;color:#111827;text-decoration:none;">TITLE</a>
  <div style="margin-top:8px;font-size:12px;color:#374151;line-height:1.5;">
    <div>🔍 ONE_SENTENCE_WHAT_HAPPENED</div>
    <div style="margin-top:2px;">👤 ONE_SENTENCE_WHO_AFFECTED</div>
    <div style="margin-top:2px;">✅ ONE_SENTENCE_WHAT_TO_DO</div>
  </div>
  <div style="margin-top:8px;font-size:11px;color:#6d28d9;">🎯 [TACTIC] TID · TECHNIQUE_NAME</div>
</div>

<!-- ALSO TODAY -->
<div style="background:white;border-radius:8px;padding:12px 16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="font-size:14px;font-weight:bold;color:#111827;margin-bottom:8px;">Also Today</div>
  <div style="padding:5px 0;border-bottom:1px solid #f3f4f6;font-size:12px;">
    <span style="background:SEVERITY_COLOR;color:white;font-size:10px;font-weight:bold;padding:1px 5px;border-radius:2px;margin-right:5px;">SEVERITY</span>
    <a href="URL" style="color:#374151;text-decoration:none;">TITLE</a>
    <span style="color:#9ca3af;"> · SOURCE</span>
  </div>
</div>

<!-- CTA -->
<div style="text-align:center;margin-bottom:16px;">
  <a href="https://metap00.github.io/Cybersecurity_News/summaries/YYYY-MM-DD.html" style="display:inline-block;background:#4f46e5;color:white;padding:12px 24px;border-radius:6px;font-size:14px;font-weight:bold;text-decoration:none;">Open Full Digest with ATT&CK Analysis →</a>
  <div style="font-size:11px;color:#9ca3af;margin-top:6px;">Full analysis · Today I Learned · Glossary · Threat actor cards</div>
</div>

<!-- FOOTER -->
<div style="text-align:center;font-size:11px;color:#9ca3af;padding-bottom:16px;">
  Generated by Claude · DATE
</div>

</body>
</html>
```

---

## Rules
- 24-hour window only — skip older articles
- Deduplicate cross-feed stories
- All titles must be hyperlinked
- Full version: `summaries/YYYY-MM-DD.html` — Compact email: `summaries/YYYY-MM-DD-email.html`
- Never fabricate content
- Quiet day (fewer than 3 articles): note it in the banner
- Every story in the full version: title is the `<summary>` toggle, full analysis inside nested `<details>` — NO `open` attribute on either
- Threat actor card only when a named group is explicitly mentioned
- Week in Review only on Sundays
- ATT&CK tag must always be specific to the story, never generic
