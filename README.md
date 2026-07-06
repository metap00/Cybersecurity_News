# 🛡 Cybersecurity News Digest

An automated daily cybersecurity intelligence agent that monitors 10 threat feeds, scores stories by severity, maps attacks to the MITRE ATT&CK framework, and delivers a formatted digest every morning at 6:30am.

**[Browse all digests →](https://metap00.github.io/Cybersecurity_News/)**

---

## How It Works

```
Claude Cloud Agent (6:30am daily, Anthropic infrastructure)
  → Reads 10 RSS feeds (Bleeping Computer, Krebs, CISA, SANS, etc.)
  → Scores articles: CRITICAL / HIGH / MEDIUM / LOW
  → Fetches full content for top 5–7 high-priority stories
  → Maps each story to MITRE ATT&CK tactic + technique
  → Identifies threat actors (APT groups, criminal gangs)
  → Writes educational sections (Today I Learned, Glossary)
  → Pushes HTML digest to GitHub

GitHub Actions (triggers on push)
  → Sends compact teaser email via Gmail SMTP

GitHub Pages
  → Hosts full interactive digest with expandable analysis
```

## Features

- **Color-coded severity** — CRITICAL / HIGH / MEDIUM / LOW with visual indicators
- **MITRE ATT&CK mapping** — every top story tagged with tactic, technique ID, and contextual explanation
- **Threat actor cards** — when named APT groups or criminal gangs appear
- **Two-tier fetching** — RSS metadata for all stories, full article content for high-priority only (token-efficient)
- **Educational content** — "Today I Learned" concept + glossary, non-repeating within 7 days
- **Weekly recap** — every Sunday, a summary of the week's threat landscape
- **Two-format delivery** — compact email for quick morning scan, full interactive page for deep reading

## Tech Stack

| Component | Technology |
|---|---|
| AI Agent | Claude Sonnet 4.6 (Anthropic) |
| Scheduling | Claude Code Cloud Routines |
| Feed parsing | RSS/OPML — no third-party API |
| Hosting | GitHub Pages |
| Email delivery | GitHub Actions + Gmail SMTP |
| Threat framework | MITRE ATT&CK |

## Monitored Feeds

Bleeping Computer · Krebs on Security · The Hacker News · SANS ISC · CISA Advisories · Ars Technica Security · Schneier on Security · SecurityWeek · Dark Reading · Graham Cluley

## Architecture Notes

The agent runs entirely in Anthropic's cloud — no local machine required. A `history.json` file in the repo serves as the agent's weekly memory, preventing repetition of educational content across runs. Two output files per day:

- `summaries/YYYY-MM-DD.html` — full interactive digest (GitHub Pages, collapsible sections)
- `summaries/YYYY-MM-DD-email.html` — compact teaser with link to full page

---
*Automated with Claude Code · Runs daily at 6:30am*
