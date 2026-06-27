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

**4. Fetch full content** for all CRITICAL and HIGH articles via WebFetch (max 7 total). Deduplicate cross-feed stories — cover once using most detailed source.

**5. Determine threat level:**
- 🔴 ELEVATED `#dc2626` — any CRITICAL story present
- 🟠 ACTIVE `#ea580c` — 2+ HIGH, no CRITICAL
- 🟡 MODERATE `#ca8a04` — 1 HIGH or mostly MEDIUM
- 🟢 QUIET `#16a34a` — nothing significant

**6. Check recent history** — read `history.json` from the repo root if it exists:
```json
{
  "til": ["last 7 concept names here"],
  "glossary": ["last 50 terms here"]
}
```
Do NOT repeat any TIL concept or glossary term found in this file. If the file does not exist, start fresh with no restrictions.

**7. Pick "Today I Learned"** — one concept from today's news a cybersecurity beginner would benefit from. Write exactly 3 sentences in plain English.

**8. Build glossary** — every acronym/jargon term used today (CVE, APT, RCE, CVSS, etc.) with a one-sentence definition each.

**9. Write output** to `summaries/YYYY-MM-DD.html` as a complete HTML file using the structure below.

**10. Update `history.json`** — update the file with today's entries:
- Add today's TIL concept to `til` array (keep only the last 7)
- Add today's new glossary terms to `glossary` array (keep only the last 50)
- Save the file to the repo root as `history.json`

**11. Commit and push** using the GitHub PAT provided in your session prompt:
```bash
git remote set-url origin https://YOUR_PAT@github.com/metap00/Cybersecurity_News.git
git config user.email "noreply@anthropic.com"
git config user.name "Cybersecurity News Agent"
git add summaries/ history.json
git commit -m "Daily digest: $(date +%Y-%m-%d)"
git push origin HEAD:main
```

## HTML Output Structure

Use **inline styles only**. Use `<details>/<summary>` for all collapsible sections.

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;background:#f3f4f6;padding:16px;">

<!-- THREAT BANNER -->
<div style="background:THREAT_COLOR;color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.85;">EMOJI THREAT_LEVEL</div>
  <div style="font-size:20px;font-weight:bold;margin-top:4px;">Cybersecurity News — DATE</div>
  <div style="font-size:13px;opacity:.85;margin-top:4px;">N stories · N critical · N high · N medium</div>
</div>

<!-- STORY CARD (repeat for each CRITICAL/HIGH/MEDIUM story) -->
<div style="background:white;border-left:4px solid SEVERITY_COLOR;border-radius:4px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <div style="margin-bottom:8px;">
    <span style="background:SEVERITY_COLOR;color:white;font-size:11px;font-weight:bold;padding:2px 8px;border-radius:3px;">SEVERITY</span>
    <span style="font-size:12px;color:#6b7280;margin-left:8px;">SOURCE · X hours ago</span>
  </div>
  <a href="URL" style="font-size:15px;font-weight:bold;color:#111827;text-decoration:none;">TITLE</a>
  <div style="margin-top:10px;font-size:13px;color:#374151;line-height:1.6;">
    <div>🔍 <strong>What happened:</strong> ONE_SENTENCE</div>
    <div style="margin-top:3px;">👤 <strong>Who's affected:</strong> ONE_SENTENCE</div>
    <div style="margin-top:3px;">✅ <strong>What to do:</strong> ONE_SENTENCE</div>
  </div>
  <details style="margin-top:10px;">
    <summary style="font-size:13px;color:#4f46e5;cursor:pointer;font-weight:500;">▶ Full analysis &amp; beginner explanation</summary>
    <div style="margin-top:10px;padding:12px;background:#f8fafc;border-radius:4px;font-size:13px;color:#374151;line-height:1.6;">
      FULL_ANALYSIS_2_TO_4_PARAGRAPHS
      <div style="margin-top:10px;padding:10px;background:#eff6ff;border-radius:4px;border-left:3px solid #3b82f6;">
        <strong style="color:#1d4ed8;">🎓 For beginners:</strong> PLAIN_ENGLISH_EXPLANATION
      </div>
      <div style="margin-top:8px;font-size:12px;color:#6b7280;">CVE-ID · CVSS: X.X/10 — ONE_SENTENCE_EXPLAINING_THE_SCORE</div>
    </div>
  </details>
</div>

<!-- TODAY I LEARNED -->
<details style="background:white;border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);">
  <summary style="font-size:15px;font-weight:bold;color:#111827;cursor:pointer;">💡 Today I Learned: CONCEPT_NAME ▶</summary>
  <div style="margin-top:10px;padding:12px;background:#f0fdf4;border-radius:4px;font-size:13px;color:#374151;line-height:1.6;">
    THREE_SENTENCE_BEGINNER_EXPLANATION
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

## Rules
- 24-hour window only — skip older articles
- Deduplicate cross-feed stories
- All titles must be hyperlinked
- Save as `summaries/YYYY-MM-DD.html` (not .md)
- Never fabricate content
- If fewer than 3 articles today, note it was a quiet day in the banner
- Every story card MUST wrap the full analysis in `<details>` with NO `open` attribute — closed by default. Only the 3-line summary is visible without clicking.
