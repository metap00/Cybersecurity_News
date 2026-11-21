# PLAN-sources: better sources, no repeats, updates marked

Owner feedback after the first briefs: *"you didn't change the news part itself: same sites, mostly the same. Research what to add or remove, which sources are credible, and make the same story not repeat over several days, unless there is something new, and then point out what's new."*

- **Status:** plan only. Nothing here is built. Every number was measured on 2026-11-21 from the VPS and from a home connection, unless a line says otherwise.
- **Workers:** start at [section 7](#7-implementation-3-tasks). Contracts are in [section 6](#6-contract-changes).
- **Owner:** four decisions with defaults are in [section 8](#8-owner-decisions-and-what-is-cut).

## In one screen

**Sources**

1. Remove 4 of the 10 feeds: CISA Advisories (blocked for the VPS), Schneier and Graham Cluley (commentary), Dark Reading (158 characters of text per story).
2. Keep 6. Bleeping Computer comes back with a one-line fix: the block was the collector's own outdated `Chrome/131` User-Agent, not the VPS.
3. Add 12, for 18 in total: 10 first-hand sources (CISA KEV, CERT-EU, NCSC, Microsoft, Google/Mandiant, Talos, Unit 42, Securelist, Proofpoint, The DFIR Report), DNSC for Romania, and The Record.
4. Every source gets a tier. 1: first-hand. 2: newsroom. 3: aggregator. The brief cites the lowest tier that covers the event.
5. The Hacker News stays as a radar only: at most 1 story per brief is cited to it, at most 2 to any other source. The limit gives way only when a brief would have fewer than 3 stories.

**Repeats and updates**

1. The pipeline remembers every story it sent for 14 days: CVEs, names, and the text the reader was told.
2. The triage model matches each new item against that memory. Same story, nothing new: skipped. A material change (patch, exploitation confirmed, public exploit, attribution, new victims): sent as "🔄 Update" with one line "What's new since <date>" and a one-line reminder.
3. The critic checks the "new" line twice: it must be in today's sources, and it must not be in what the reader was already told. Code allows one patch, one exploitation, one exploit and one attribution update per story.

**Tasks:** T1 writer, critic and renderer learn several sources per story and update items (inert alone). T2 feed list, tiers, KEV as a source, fetch fixes, source cap. T3 story memory. T1 and T2 in parallel, then T3.

## 1. Before and after

| | Today | After |
|---|---|---|
| Sources | 10 feeds. 2 fail from the VPS on every run. 2 are commentary blogs. 6 give the models under 400 characters per story | 18 sources, all answering from the VPS: 11 first-hand, 6 tier 2, 1 aggregator |
| Where stories come from | The Hacker News: 7 of 15 candidates and 3 of the 4 stories sent on 2026-11-21 | At most 1 story per brief cited to an aggregator, at most 2 to any other source |
| One event, several feeds | Merged only on the same URL, a shared CVE or a near-identical title. In a 72-hour sample, 10 events had two or more feeds: code merged 3 of them, two only in part, and made 1 wrong merge | The triage model groups them. Code cites the most first-hand member. Writer and critic read every member's text |
| Same story on later days | Dropped only when a CVE or a URL repeats. A story without a CVE comes back when another outlet writes about it. A real development on a CVE story can never be shown | 14-day story memory. Repeat: skipped. Material change: sent as an update |
| "What's new" | Does not exist | One line, written from today's sources, checked by the critic against what the reader was already told |

## 2. Findings

### 2.1 What the data says

| # | Finding | Evidence |
|---|---|---|
| 1 | **One site dominates** | Old archive, 125 daily pages, 732 outside links: The Hacker News 228 (31%, on 80 of 125 days), Bleeping Computer 114, SecurityWeek 92. Those three: 59%. New pipeline, 2026-11-21: The Hacker News gave 7 of 15 candidates and 3 of 4 sent stories |
| 2 | **Two feeds were never cited** | Same archive: Schneier 0 links, Graham Cluley 0, with both feed URLs working. Krebs: 3. The counts for SANS ISC (0), Ars Technica (0), Dark Reading (5) and CISA (21) are not a fair test: `PLAN.md` found their old feed URLs failing |
| 3 | **Two feeds fail on every VPS run** | Three runs on 2026-11-21, the only day of logs: `8/10 feeds ok`, with 403 for Bleeping Computer and CISA each time. Causes in 2.2 |
| 4 | **The models work from teasers** | The critic accepts only facts that are in the feed text. Median text per item: SANS ISC 31 characters, Dark Reading 158, Bleeping Computer 189, SecurityWeek 229, The Hacker News 393. First-hand research feeds carry the full article: Talos 10,223, Securelist 20,977, Microsoft 21,410, Google 27,623 (the collector keeps the first 1,200) |
| 5 | **The same story did repeat inside one brief** | 2026-11-21 sent "CISA adds four actively exploited flaws, including VMware vCenter, to KEV" and "China-linked group 'Armory Castle' attacks VMware vCenter with a zero-day" as two stories. Same flaw, two feeds, no shared CVE in the feed text |
| 6 | **Code merging misses most overlaps** | 72 hours of the new feed list, 74 items. Events with two or more feeds: vCenter zero-day, PHP fixes, the Cairn AI-agent zero-day, N-able breach, the Chase/Visa/Mastercard vendor breach, SBC Medical, NGINX, F5 BIG-IP, WhatsApp, Ruby. Merged by code: WhatsApp, vCenter (2 of 7 items), NGINX (2 of 4 items) |
| 7 | **A shared CVE is not proof of the same story** | The fourth merge in that sample was wrong: a SANS guest diary about honeypot workflow and an unrelated Hacker News article ("Everything Is a Web Application, Including Your Firewall"), joined because both mention CVE-2026-109618 in passing |
| 8 | **One story is written about for days** | The vCenter zero-day, 19 to 21 November: Google Threat Intelligence (the first-hand report), SecurityWeek, Bleeping Computer, The Hacker News three times, DNSC, Dark Reading, then CISA's KEV listing. Nine items in three days |

### 2.2 Why two feeds fail from the VPS

| Feed | What the test showed | Cause | Fix |
|---|---|---|---|
| Bleeping Computer | 403 with the collector's User-Agent, from the VPS **and** from a home connection. Header: `cf-mitigated: challenge`. 200 from the VPS with six other strings: curl's default, Chrome 142, Firefox 140, FreshRSS, Miniflux, a generic reader string | Cloudflare challenges the outdated `Chrome/131` string in `brief/collect.py`. The VPS address is not blocked | Change the User-Agent (section 3.2) |
| CISA (every `cisa.gov` URL, the KEV JSON too) | 403 "Access Denied" from the VPS for curl, wget and Python, 6 User-Agents, HTTP/1.1 and HTTP/2, IPv4 and IPv6. From home: 200 with curl, 403 with Python | Akamai refuses the VPS's network. None of those settings changes it | Stop fetching `cisa.gov`. Use CISA's own GitHub copy of KEV, which the collector already downloads: 200 from the VPS and the same 1,871,127 bytes as the `cisa.gov` file |

A browser User-Agent is a moving target: Chrome 142 fixed Bleeping Computer but got 403 from Schneier. The generic reader string got 200 from every feed on the final list, through both fetch paths (Python and curl). Microsoft is the one feed that needs a note: see below the tables in 3.1.

### 2.3 The 10 current feeds

Items per day: items dated in the last 7 days, divided by 7. Text: median characters per item after HTML is stripped. Archive: links in the 125 old daily pages; a star marks the four feeds whose old URL was failing (finding 2).

| Feed | Tier | From the VPS | Items/day | Text | Archive | Verdict |
|---|---|---|---|---|---|---|
| Krebs on Security | 2 | 200 | 0.3 | 6,030 | 3 | **Keep.** Original investigations, full text in the feed |
| The Hacker News | 3 | 200 | 9.7 | 393 | 228 | **Keep as radar.** Fast and broad, but it rewrites other people's research and mixes in sponsored posts. Never cited when a tier 1 or 2 source has the event. Max 1 story per brief |
| Bleeping Computer | 2 | 403, then 200 with the new User-Agent | 7.5 | 189 | 114 | **Keep, fix the fetch.** Original, fast, technical breaking news |
| SANS Internet Storm Center | 1 | 200 | 1.7 | 31 | 0* | **Keep, change the URL** to `rssfeed_full.xml`: diaries then carry 2,000+ characters. Analyst diaries on logs, malware and honeypots are the closest thing to SOC work on the list |
| CISA Advisories | 1 | 403, every client | 2.6 | 4,882 | 21* | **Remove.** Unreachable from the VPS. KEV through GitHub replaces it for exploited flaws |
| Ars Technica Security | 2 | 200 | 0.7 | 1,279 | 0* | **Keep.** Few stories, original, well explained, enough text |
| Schneier on Security | commentary | 200 | 0.9 | 691 | 0 | **Remove.** Essays and comment on stories reported elsewhere, plus a weekly squid post. `profile.md` says skip opinion |
| SecurityWeek | 2 | 200 | 5.3 | 229 | 92 | **Keep.** A second independent newsroom next to Bleeping Computer |
| Dark Reading | 2 | 200 | 3.3 | 158 | 5* | **Remove.** The thinnest text of all. 2 of its 3 items on 2026-11-21 were columns. Its news is on Bleeping Computer, The Record and SecurityWeek |
| Graham Cluley | commentary | 200 | 0.4 | 268 | 0 | **Remove.** Link posts and podcast episodes, no reporting of its own |

### 2.4 Checked and not added

| Source | What the check found | Verdict |
|---|---|---|
| NVD API, CVE.org API, EPSS API | All three answer 200 from the VPS. They are databases, not news: tens of thousands of CVEs a year, and NIST [announced in April 2026](https://www.nist.gov/news-events/news/2026/04/nist-updates-nvd-operations-address-record-cve-growth) that it enriches only priority CVEs, KEV entries among them | Not a source. KEV is the filter that matters. Useful later only to add a CVSS or EPSS number |
| Microsoft MSRC | The blog feed URL now returns an HTML page. That page links no feed, and three likely feed paths return 404. The Update Guide RSS is 3.3 MB with 5,781 rows, one per CVE | Not usable. Patch Tuesday arrives through SANS ISC, Talos, Krebs and Bleeping Computer |
| ENISA | No RSS: 8 URL patterns return 404 and the news page links no feed. Its vulnerability database (EUVD) has a working API, but 98 of its latest 100 exploited entries are already in KEV | Not added. CERT-EU is the EU source |
| CISA advisories through FeedBurner | `feeds.feedburner.com/cisa/oeasXGj8IGF` answers from the VPS with CISA's joint advisories. CISA's own subscribe page does not list it, so its owner is unknown | Not added. An unofficial copy cannot be a first-hand source |
| FBI IC3 industry alerts | 200 from the VPS. Titles and PDF links only | Not added: no text to check facts against |
| ESET WeLiveSecurity | 200, 0.4 a day, 127-character teasers, mostly consumer advice | Not added. ESET's research reaches the brief through the newsrooms |
| Sophos, CrowdStrike | Sophos: the site feed times out, the FeedBurner copy has 134-character teasers. CrowdStrike: titles only | Not added |
| Check Point Research, SentinelLabs, Rapid7 | All 200 with full text. More vendor labs with the same kind of content as the six on the list; Rapid7 mixes in product posts (1.4 a day) | Not added. First candidates if a lab on the list goes quiet |
| Elastic Security Labs, Red Canary, Huntress | Elastic: the feed is over 6 MB. Red Canary: no post since 2026-08-20. Huntress: 403 | Not added |
| Chrome Releases, Google Security Blog | Chrome Releases: 1.6 a day, every release channel in one feed. Google Security Blog: last post 2026-04-23 | Not added. A Chrome zero-day reaches the brief through the newsrooms |
| The Register (security), CyberScoop | Both 200 with full text (3,843 and 3,976 characters). The Register: 5.6 a day. CyberScoop: 2.6 a day, mostly US policy | Not added. The Register is the first spare if a newsroom on the list fails |
| Risky Bulletin | 200, full text. Each item is a whole newsletter with dozens of stories, so it cannot be one candidate | Not added. Good for a manual weekend read |
| Help Net Security, Security Affairs, Infosecurity Magazine | 200. Aggregators, 4 to 5 a day each | Not added. One radar is enough |
| TechCrunch, Wired, Troy Hunt | 200. Teasers of 135 to 175 characters, consumer angle, or under 1 post a week | Not added |

## 3. Final feed list

18 sources: 17 feeds in `feeds.opml` and the KEV catalog, which the collector already downloads. About 34 items a day, against 22 reachable today. The Hacker News falls from 43% of the items to 28%.

### 3.1 The list

Every URL returned 200 from the VPS with the User-Agent of section 3.2, through Python and through curl.

**Tier 1: first-hand.** The organisation publishes its own findings, advisories or decisions.

| # | Source (name shown in the brief) | URL | Volume | Text | Why |
|---|---|---|---|---|---|
| 1 | CISA KEV | `https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json` (JSON, section 3.3) | 60 flaws on 24 days since 1 October | built by code | The US agency's list of flaws with evidence of exploitation. The clearest "patch this first" signal |
| 2 | CERT-EU | `https://cert.europa.eu/publications/security-advisories-rss` | 1 a week | 445 | The EU institutions' CERT. One advisory per flaw that matters in companies, with CVEs and what to do |
| 3 | NCSC (UK) | `https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml` | 2 a week | 127 | UK national authority. Co-signs many joint advisories with CISA and the FBI, and names attackers. Mostly guidance, which triage skips |
| 4 | Microsoft Threat Intelligence | `https://www.microsoft.com/en-us/security/blog/topic/threat-intelligence/feed/` | 2 to 5 a week | 21,410 | Own research on attacks against Windows, Entra ID and Azure: the reader's cloud path. See the note on bursts below |
| 5 | Google Threat Intelligence | `https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v` | 1 a week | 27,623 | Mandiant's incident response reports. Its report was the first-hand source of the vCenter story. The feed is the one Google's own blog page links |
| 6 | Cisco Talos | `https://blog.talosintelligence.com/rss/` | 4 a week | 10,223 | Research, a weekly threat roundup, Patch Tuesday notes |
| 7 | Unit 42 | `https://unit42.paloaltonetworks.com/feed/` | 3 a week | 243 | Palo Alto's research team. Teaser-only feed, so it is mostly cited next to a newsroom's text |
| 8 | Kaspersky Securelist | `https://securelist.com/feed/` | 5 a week | 20,977 | Detailed malware and APT analysis. Russian vendor, banned from US sales in 2024: decision D2 |
| 9 | Proofpoint Threat Insight | `https://www.proofpoint.com/us/threat-insight-blog.xml` | 3 a month | 13,089 | Email and phishing campaigns: the reader's phishing analysis module |
| 10 | The DFIR Report | `https://thedfirreport.com/feed/` | 1 every 1 to 3 months | 468 | Full intrusion walk-throughs mapped to ATT&CK. The best "learn" material there is, at almost no volume |
| 11 | SANS Internet Storm Center | `https://isc.sans.edu/rssfeed_full.xml` | 1.7 a day, half of it a podcast entry | 2,000+ for diaries | See 2.3 |

**Tier 2: newsrooms that confirm with their own sources, and CERT relays.**

| # | Source | URL | Volume | Text | Why |
|---|---|---|---|---|---|
| 12 | DNSC (Romania) | `https://dnsc.ro/feed` | 4 a week | 98 | Romania's national authority, in Romanian. First-hand for campaigns against Romanians, where it is the only source and is cited. For world-wide flaws it relays the vendor's bulletin, so an English source wins the citation: decision D1 |
| 13 | Krebs on Security | `https://krebsonsecurity.com/feed/` | 2 a week | 6,030 | See 2.3 |
| 14 | Bleeping Computer | `https://www.bleepingcomputer.com/feed/` | 7.5 a day | 189 | See 2.3 |
| 15 | The Record | `https://therecord.media/feed` | 5 a day | 183 | Original reporting on cybercrime, state attackers and policy. The feed holds only the 5 newest items, so a daily fetch sees part of a busy day |
| 16 | Ars Technica Security | `https://arstechnica.com/security/feed/` | 0.7 a day | 1,279 | See 2.3 |
| 17 | SecurityWeek | `https://www.securityweek.com/feed/` | 5.3 a day | 229 | See 2.3 |

**Tier 3: aggregator.**

| # | Source | URL | Volume | Text | Why |
|---|---|---|---|---|---|
| 18 | The Hacker News | `https://feeds.feedburner.com/TheHackersNews` | 9.7 a day | 393 | Radar. It often reports research from vendors that are not on this list |

Microsoft's site answers 403 to about half of the requests that arrive within seconds of each other, then 200 again. 5 of 5 fetches spaced 20 seconds apart succeeded. One fetch a day is fine; the third attempt in section 3.2 covers a bad moment.

### 3.2 Fetch settings

| Setting | Now | New | Why |
|---|---|---|---|
| User-Agent | `Mozilla/5.0 … Chrome/131.0.0.0 Safari/537.36` | `Mozilla/5.0 (compatible; rss-reader/1.0)` | See 2.2. No browser version to go stale, no name, email or repo in it |
| Attempts | 2: Python, then curl | 3: Python, curl, then curl again after 3 seconds | Microsoft's burst limit |
| Size cap per feed | 3 MB | 8 MB | Google's feed is 1.7 MB today and carries whole articles |
| Run fails when | fewer than 3 of 10 feeds answer | fewer than 6 of 18 sources answer | Same share as before |
| CVE keys | every CVE in the whole feed text | CVEs in the title and the first 1,200 characters | Full-text feeds name CVEs far down the page. In the sample, a Talos newsletter names CVE-2026-114938 only after character 1,200, and Google's vCenter report names 4 CVEs, 2 of them only further down. Keys should come from the text the models see |

### 3.3 KEV as a source

Today KEV only sets the `kev` flag on other feeds' stories. New: KEV entries become a candidate of their own, built by code from CISA's JSON. No model writes any of it.

| Part | Rule |
|---|---|
| When | One candidate per `dateAdded` value that is on or after the date of `since`. CISA publishes during the US working day, so each batch is offered once, on the next morning's run |
| `feed`, `tier` | `CISA KEV`, 1 |
| `title` | 1 entry: `CISA KEV adds an exploited flaw in <vendorProject> <product>`. More: `CISA KEV adds <n> exploited flaws: <vendorProject product>, …` |
| `summary` | Per entry: `<vendorProject> <product> (<cveID>): <shortDescription> Ransomware use: <knownRansomwareCampaignUse>. US federal deadline: <dueDate>.` Cut at 1,200 characters |
| `url` | 1 entry: `https://www.cisa.gov/known-exploited-vulnerabilities-catalog?field_cve=<cveID>` (checked: the page shows that one flaw). More: the catalog page without a query (newest first). The reader's phone opens `cisa.gov` normally; only the VPS is blocked |
| `keys` | One `cve-…` per entry and `kev:<dateAdded>`. No `u:` key: the catalog URL is the same every day and would block every later batch |
| Merging | Added after the collector's merge and never merged by code. A batch of four flaws that merged on a shared CVE would pull four unrelated stories into one. Until T3 the critic sorts out an overlap, as today; from T3 the triage model groups it |
| Health table | A row `CISA KEV` like any feed. If the download fails: warn, no candidate, `kev` flags false, as today |

## 4. Story memory

One line: **keys propose, the model decides, the critic checks, code enforces.**

### 4.1 Rules

| Case | What the reader gets |
|---|---|
| A candidate continues a story sent in the last 14 days and adds nothing material | Nothing. One log line: `[triage] c07: repeat of 2026-11-21-c09, nothing new` |
| It adds something material | An update item: "🔄 Update", the "What's new since <date>" line, a one-line reminder |
| The same article URL was already used | Dropped by code before any model sees it, as today |
| A story's last send is more than 14 days ago | Treated as new |

**Material** means today's sources state one of these, and the reader was not told it before:

| `type` | Counts | Does not count |
|---|---|---|
| `patch` | A fix, a fixed version or an official mitigation now exists | "A patch is coming", the vendor repeating its advice |
| `exploited` | Attacks in the wild are confirmed for the first time (vendor, researcher or KEV), or went from a few targets to mass exploitation | A KEV listing of a flaw the reader was already told is exploited |
| `poc` | Working exploit code or the full technical details are public for the first time | Another write-up of the same analysis |
| `attribution` | A named group, state or person is tied to it for the first time: a vendor report, a government statement, charges, an arrest | "Possibly linked to", repeated |
| `victims` | New named victims, a confirmed breach, or a materially larger count or scope | Reactions, comment, a recap |

More coverage, analysis, "explained" pieces, roundups and vendor marketing are never an update.

Code adds one hard rule: **`patch`, `exploited`, `poc` and `attribution` can each be sent once per story.** A second `patch` update for the same story is a repeat, whatever the model says. `victims` may recur.

### 4.2 How a story is recognised

No embeddings. 50 to 60 stories are in memory at any time, so the model can read all of them.

| Step | Who | What |
|---|---|---|
| 1 Keys | code | Each sent story keeps its CVE IDs, the URLs of every article used, and up to 4 names (the group, the malware, the victim, the vendor with the product). Names are chosen by the triage model and kept only if they appear in the feed text, letter for letter |
| 2 Hints | code | For each candidate: `seen` = sent stories that share a CVE with it or whose name appears in its title or summary. A hint, not a verdict (finding 7) |
| 3 Decision | triage model | Reads the candidate, the hints and the memory (headline, dates, names, CVEs and what the reader was told). Returns `story` (which sent story this continues, or none), `update` (one of the five types, or `none`) and `new` (the new fact, max 25 words) |
| 4 Enforcement | code | Repeat: dropped and logged. Update: goes on with the story's record attached. The once-per-type rule. Max 2 updates in a brief. `since` comes from the record, never from a model |
| 5 Draft | writer | Writes the what's-new line from today's sources and the reminder from what was told before |
| 6 Check | critic | Section 4.5. Also drops a normal item that repeats a sent story |
| 7 Record | code | After a successful send: a new record, or the update added to the old one |

A model can fail in three ways. Each has a guard.

| Failure | Guard |
|---|---|
| A repeat is judged new | The critic sees the list of sent stories and drops it (`repeat of <id>`). Each such drop is a triage miss: count them |
| A repeat is dressed up as an update | The once-per-type rule, then the critic's "is it really new" check |
| A new story is judged a repeat and vanishes | Every skip is logged with the story it matched. Review the log in the first two weeks. This is the one failure the reader cannot see |

### 4.3 Where the state lives

`data/state.json`, new top-level key `stories`, written only by `brief/state.py`, at send time, next to the glossary and TIL memory. One file, one writer, as now.

```jsonc
"stories": [   // one per story sent; removed when "last" is more than 14 days old
  {
    "id": "2026-11-21-c09",            // date first sent + that day's item id
    "first": "2026-11-21",
    "last": "2026-11-21",              // date of the latest send: the original or an update
    "headline": "China-linked group Armory Castle exploits VMware vCenter zero-day",
    "keys": ["u:www.darkreading.com/…"],   // the CVE and URL keys of every member, over all sends
    "names": ["Armory Castle", "VMware vCenter"],
    "told": [                          // what the reader was told, oldest first: the baseline for "new"
      {"date": "2026-11-21", "type": "first", "text": "<the summary as sent>"},
      {"date": "2026-11-24", "type": "patch", "text": "<the what's-new line as sent>"}
    ]
  }
]
```

- **No migration.** When the key is missing, `state.stories()` builds the records from `data/digests/*.json` of the last 14 days, the same way `state.polls()` converts old days on read. The first run after the deploy already knows what was sent before.
- `days[].keys` and `days[].titles` stay as they are. The collector's URL drop keeps reading `days[].keys`.
- Items in a digest's `also` list were never shown, so they are not remembered.
- `send --force` for a date first removes that date's records and that date's `told` entries.

### 4.4 What the reader sees

Built from two real headlines of 19 November (The Hacker News in the morning, Bleeping Computer in the afternoon), as it would look on the 20th:

```text
🔄 Update: PHP ships the fixes for its critical flaws
What's new since 19 Nov: The patched PHP versions are out. They fix 18 flaws, including
critical remote code execution bugs.
Reminder: PHP had warned that critical flaws affect every supported version and promised
fixes for 19 November.
Why it matters to you: …
Source: Bleeping Computer
```

- "🔄 Update:" replaces the 🔴🟠🟡 marker. The date is the story's `last`: the last time the reader heard about it.
- An update is about half the size of a new story: no 40-80 word summary, the reminder takes its place.
- The ATT&CK line, the actor line and the quiz work as for any item.

### 4.5 How the critic verifies "new"

For an update item the critic gets today's sources (every member's text) and `previous.told`. It checks in this order:

1. **Same story.** Today's sources are about the same event as `previous`. If not: `drop`, issue `not the same story`.
2. **Supported.** Every fact in `new` is in today's sources.
3. **New.** No fact in `new` is already in `previous.told`. Remove what was told before. Nothing left: `drop`, issue `nothing new`.
4. **Material.** What is left is one of the five types of 4.1 and matches the `type` that triage gave. Colour, comment or a longer description of the same facts: `drop`.
5. **Reminder.** The reminder agrees with `previous.told` and adds nothing that is in neither `previous.told` nor today's sources.

`fixed` is allowed in steps 2, 3 and 5 when a supported, new, material fact remains. Code then re-checks the caps and copies `story`, `type` and `since` from the triage record, so no model can change which story an update belongs to or its date.

### 4.6 The vCenter story, replayed

What the feeds carried is real. The right column is what this design does with it.

| Morning brief | New items since the last brief | Old pipeline | New design |
|---|---|---|---|
| 20 Nov | Google Threat Intelligence "ARMORY CASTLE Exploits vSphere", SecurityWeek, Bleeping Computer "VMware patches vCenter zero-day exploited in attacks since September", The Hacker News | Not running yet | One story. Cited to Google Threat Intelligence (tier 1). Writer and critic read all four texts |
| 21 Nov | DNSC alert, The Hacker News again, Dark Reading "China's 'Armory Castle' Lays Siege to VMware vCenter Zero-Day" | Sent the Dark Reading item as a new story | Repeats with nothing new: skipped, one log line each (Dark Reading is no longer fetched) |
| 21 Nov | CISA lists the flaw in KEV with three others (dated 20 Nov). The Hacker News writes that up a day later | Sent The Hacker News article as a second story about the same flaw | One story about the four listed flaws, cited to CISA KEV. For vCenter, "exploited" was already told, so no update. The Hacker News article a day later: repeat, skipped |
| Later | Say a public exploit appears | Dropped (shared CVE), or sent as "new" if the article has no CVE | "🔄 Update", type `poc`, with the reminder |

## 5. Original sources first

| Rule | Detail |
|---|---|
| Group | Code merges exact duplicates: same URL, or titles at least 0.85 similar. Everything else is the triage model's call: `dup_of` points a candidate at another candidate of the same run that reports the same event |
| Cite | The group's `feed` and `url` are those of the member with the lowest tier. Tie: the member with the longest text |
| Read | Writer and critic get every member's title and text, up to 4. Bleeping Computer (189 characters) plus The Record (183) plus The Hacker News (393) is three angles instead of one teaser. If members disagree, the lowest tier wins or the fact is left out |
| Limit | In one brief: max 2 stories cited to one tier 1 or 2 source, max 1 to a tier 3 source. Relaxed only to reach 3 stories |
| Backstop | The shortlist never holds two entries that share a CVE. The lower one is dropped and its feed is added to `also` |

A shared CVE no longer merges two items in the collector (finding 7). The model sees both CVE lists and decides; the backstop covers the brief.

## 6. Contract changes

Additions to `PLAN.md` section 8. Every new field is optional for the reader of the file: missing means today's behaviour.

`feeds.opml`: each `<outline>` gets `tier="1"`, `"2"` or `"3"`. Missing: 2.

`out/candidates.json`, per candidate:

```jsonc
{
  "id": "c03",
  "title": "…", "url": "…", "feed": "Google Threat Intelligence",   // now: the member with the lowest tier, then the longest text
  "tier": 1,                                                          // new
  "summary": "…",                                                     // the cited member's text
  "also": ["Bleeping Computer", "SecurityWeek"],                      // unchanged: the other members' feed names
  "sources": [                                                        // new: the other members' text, longest first, max 3; [] when alone
    {"feed": "Bleeping Computer", "tier": 2, "title": "…", "summary": "…"}
  ]
  // published, cves, kev, keys: unchanged. A KEV candidate has "kev:<date>" in keys and no "u:" key.
}
```

Triage model output, per candidate (new fields after `reason`):

```jsonc
{"id": "c07", "score": 7, "kind": "know", "reason": "…",
 "dup_of": "c03",             // another candidate of this run with the same event, or null
 "story": "2026-11-21-c09",   // a sent story this continues, or null
 "update": "patch",           // none | patch | exploited | poc | attribution | victims
 "new": "…",                  // max 25 words when update is not none, else ""
 "names": ["Armory Castle", "VMware vCenter"]}   // 0-4, copied from the candidate's text
```

`out/ranked.json`, per shortlist entry (one per group; every candidate field of the cited member is kept):

```jsonc
{
  "names": ["Armory Castle", "VMware vCenter"],
  "update": {"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21", "hint": "<triage's new line>"},   // or null
  "previous": {"headline": "…", "first": "2026-11-21",                                                           // or null
               "told": [{"date": "2026-11-21", "type": "first", "text": "…"}]}
}
```

`out/draft.json`, per item: `"new": "…"` for an update item, `null` otherwise.

`out/digest.json`, per item:

```jsonc
{
  "update": {"story": "2026-11-21-c09", "type": "patch", "since": "2026-11-21"},   // or null; copied by code
  "new": "…",                  // the what's-new line, or null
  "names": ["…"]               // copied by code
  // for an update item, "summary" holds the reminder
}
```

`data/state.json`: the `stories` list of section 4.3.

Caps, checked in code like the others:

| Part | Limit |
|---|---|
| What's-new line (`new`) | max 30 words; set exactly when the item is an update |
| Reminder (`summary` of an update item) | 15-40 words |
| Updates in one brief | max 2 |
| Stories per source in one brief | max 2; max 1 for a tier 3 source |
| Names per story | max 4, each found in the feed text |
| Story memory | 14 days after the last send |

## 7. Implementation: 3 tasks

T1 and T2 touch different source files and can be built in parallel. T3 comes after both. **Merge in the order T1, T2, T3**: T1 changes nothing until the others land, and T2 without T1 would cite a first-hand source while the models still read only its teaser.

Conventions as in `PLAN.md` section 5 and `CLAUDE.md`: standard library only, `main(argv=None) -> int`, tests without network, model text never contains a URL. Tests use canned model JSON, as `tests/test_llm_stages.py` does today.

| Task | Edits |
|---|---|
| T1 | `brief/llm.py`, `brief/write.py`, `brief/critique.py`, `prompts/write.md`, `prompts/critique.md`, `brief/deliver.py` (`render`), `tests/test_llm_stages.py`, `tests/test_deliver.py` |
| T2 | `feeds.opml`, `brief/collect.py`, `brief/triage.py` (the shortlist loop), `tests/test_collect.py`, `tests/fixtures/collect/`, `tests/test_llm_stages.py` (two triage tests, next to the existing triage tests), `README.md` |
| T3 | `brief/state.py`, `brief/triage.py`, `prompts/triage.md`, `brief/collect.py` (two rules), `brief/critique.py` and `prompts/critique.md` (the repeat check), `brief/deliver.py` (the state write), the three test files, `tests/fixtures/llm/`, `PLAN.md`, `CLAUDE.md`, `README.md` |

### T1. Writer, critic, renderer: several sources, update items. About 90 minutes

**Goal:** the model stages read every source of a story and can draft, check and show an update. With today's inputs the output does not change.

Spec

1. `brief/llm.py`: `ITEM` gets `new` (string or null, required). Constants `NEW = 30` and `REMINDER_MIN, REMINDER = 15, 40`. `check_item(it, update=False)`: for an update, `new` is a non-empty string of at most 30 words and `summary` has 15-40 words; otherwise `new` must be null and `summary` keeps 40-80.
2. `brief/write.py`: give the model `sources` (`feed`, `tier`, `title`, `summary`), `update` and `previous` of each shortlist entry. Missing: `[]`, null, null. `check_draft` calls `check_item` with the entry's update flag.
3. `brief/critique.py`: the same three fields in `<sources>`. `apply()` checks with the update flag. `build()` copies `update` (`story`, `type`, `since`) and `names` from the shortlist entry onto the digest item, never from the model, and keeps `new`. `item_words()` counts `new`.
4. `prompts/write.md`:
   - Rule 2: facts come from the item's `title` and `summary` and from the `title` and `summary` of every entry in `sources`. They report the same event. If they disagree, use the lowest `tier` or leave the fact out.
   - A source may be in Romanian. Write in English.
   - An item with `update` continues a story the reader already has; `previous.told` is what they were told. `headline`: the development, as a plain statement. `new`: one or two sentences with only what today's text adds to `previous.told`. `summary`: the reminder, one or two sentences on what the story was, from `previous.told`. For every other item `new` is null.
   - Hard limits: the two new caps.
5. `prompts/critique.md`: the five checks of section 4.5. One more rule for every item: a `sources` entry about a different event is ignored and named in `issues`.
6. `brief/deliver.py` `render`: for an item with `update`, the layout of section 4.4. `since` is printed as day and short month (`21 Nov`). Every field is read with `.get`, so a digest without the new fields renders as today.

Done when

- Tests: `new` of 31 words is rejected; `new` on a normal item is rejected; an update reminder of 41 words is rejected; `update.story` and `update.since` in `digest.json` equal the shortlist's whatever the model returned; the user prompt of `write` and of `critique` contains the text of a second source; an update item renders `🔄`, `Update:`, `What's new since 21 Nov:` and `Reminder:`; the word count includes `new`.
- `python -m brief.run --demo` prints exactly what it prints on `main`.

Check

```sh
python -m pytest -q
python -m brief.run --demo
```

### T2. Sources: feed list, tiers, KEV, fetch fixes, source cap. About 90 minutes

**Goal:** `python -m brief.collect` on the VPS reports at least 16 of 18 sources OK, Bleeping Computer among them, and a brief cites The Hacker News more than once only when it would otherwise have fewer than 3 stories.

Spec

1. `feeds.opml`: the 17 feeds of section 3.1, each with `tier`, `title` as in the "Source" column.
2. `brief/collect.py`:
   - The five settings of section 3.2.
   - `load_feeds` returns the tier with each feed.
   - `merge`: the kept member is the one with the lowest tier, then the longest summary. Write `tier` and `sources` (section 6). `also` as today.
   - KEV candidates as in section 3.3, added after `merge`. Download the catalog once and use it for both the candidates and the `kev` flag.
   - The 14-day key drop stays as it is, so until T3 a KEV batch that shares a CVE with a sent story is dropped whole, like any candidate today. T3 changes it.
3. `brief/triage.py`, shortlist loop: the size rule stays (entries with score 6 or more, at least 3, at most 5). While filling it, best score first, skip a candidate whose `feed` already has 2 entries, or 1 for `tier` 3 (missing tier: 2). If the candidates run out before 3 are taken, add the skipped ones, best first.
4. `README.md`: the feed count, the collect row of the stage table, the diagram label.

Done when

- `tests/test_collect.py`: tier read from OPML, default 2; the lowest tier is cited and a tie goes to the longest text; `sources` holds the other members' text; a CVE after character 1,200 is not a key; a KEV fixture with one entry gives the `field_cve` link and one with three gives the catalog link, both with a `kev:` key and no `u:` key; an entry dated before `since` gives no candidate; a KEV candidate does not merge with a feed item that has the same CVE; the third fetch attempt runs after two failures.
- `tests/test_llm_stages.py`: four candidates of one tier 3 feed and two of other feeds shortlist as 1 + 2; with only tier 3 candidates the shortlist still reaches 3.
- Live on the VPS, from a scratch clone of the branch (not `~/Cybersecurity_News`, which the timer runs): at least 16 of 18 rows OK, Bleeping Computer and CISA KEV among them. Paste the health table in the PR.

Check

```sh
python -m pytest -q
python -m brief.collect                 # on the VPS, from the scratch clone
python -m brief.run --dry-run           # sources and links in the rendered brief
```

### T3. Story memory. About 2.5 hours

**Goal:** a story sent in the last 14 days comes back only as a marked update, and one event is one item whatever the number of feeds.

Spec

1. `brief/state.py`:
   - `STORY_DAYS = 14`.
   - `stories(state, today) -> list`: records whose `last` is within 14 days. Without a `stories` key: built from `data/digests/*.json` (section 4.3).
   - `remember_stories(state, digest)`: per digest item, a new record, or for an update: append to `told`, set `last`, add its keys and names. Removes records older than 14 days. Called with `force`: first undo that date (section 4.3).
2. `brief/collect.py`:
   - The 14-day drop uses only keys that start with `u:` or `kev:`. A shared CVE no longer drops a candidate.
   - `_same()`: same `u:` key, or titles at least 0.85 similar. A shared CVE no longer merges.
3. `brief/triage.py`:
   - Input: `<sent_stories>` from `state.stories()` with `id`, `first`, `last`, `headline`, `names`, the CVEs from `keys`, and `told` (each story's `told` text cut at 120 words). Candidates get `tier` and `seen`: ids of sent stories that share a CVE, or whose name (4 characters or more) appears as a whole word in the title or summary.
   - Output schema: section 6. Checks, with the existing one retry: `dup_of` is another existing id; `story` is a sent id or null; `update` is `none` when `story` is null; `new` is filled exactly when `update` is not `none`, max 25 words.
   - Groups: candidates linked by `dup_of`, and all candidates that name the same `story`. One entry per group: cited member by tier then text length; `sources`, `also`, `keys`, `cves` are the union; the score and `kind` of the best member.
   - A group with a `story`: no member has an update, or the type is `patch`, `exploited`, `poc` or `attribution` and the story's `told` already has it: dropped as a repeat, with the log line of 4.1. Otherwise: `update` with `since` = the story's `last`, and `previous`.
   - `names`: kept when found in the group's text, case-insensitive; max 4.
   - Shortlist loop, on top of T2's source cap: skip a third update; skip an entry that shares a CVE with one already taken and add its feed to that one's `also`. The fill-up to 3 takes only source-cap skips.
   - Log a candidate that has `seen` but `story` null: `[triage] c05: shares CVE-… with 2026-11-21-c06, judged a different story`.
4. `prompts/triage.md`: the four new fields with the table of 4.1. "Give every member of a group the same `story` and `update`." "Two candidates with the same CVE are usually the same event, unless one only mentions it in passing." Add to `skip`: sponsored posts, podcast episodes, weekly roundups.
5. `brief/critique.py` and `prompts/critique.md`: a `<sent_stories>` block (`id`, `last`, `headline`, `names`). A normal item that repeats one of them: `drop`, issue `repeat of <id>`.
6. `brief/deliver.py`: call `st.remember_stories(s, digest)` where `remember(s, digest)` is called.
7. Docs: `PLAN.md` section 8 gets one line that points here. `CLAUDE.md`: the caps of section 6 on the rules line, `stories` on the `data/` line. `README.md`: the story memory in the stage table and one design-decision paragraph.

Done when

- Tests, state: a sent item creates a record; an update appends to `told` and moves `last`; a record 15 days old is removed; without a `stories` key the records come from the digest files; `--force` replaces the day's records.
- Tests, collect: a candidate that shares only a CVE with a sent day is kept; one that shares a URL is dropped; two items with one CVE and different titles stay two candidates.
- Tests, triage: a repeat is not shortlisted and is logged; an update is shortlisted with `since` = the story's `last` and with `previous`; a second `patch` for a story that has one is dropped; three feeds on one event give one entry cited to the tier 1 member with the other two texts in `sources`; an unknown `dup_of` triggers the retry; a name that is not in the text is discarded; a third update is skipped; two entries sharing a CVE become one.
- Tests, critique: a normal item with verdict `drop` and issue `repeat of …` is not in the digest.
- **Live replay, 3 runs, real model, no send.** Memory: the four stories of `examples/digest.json`. Five hand-written candidates in `tests/fixtures/llm/replay.json`:
  1. an aggregator's rewrite of the Armory Castle vCenter story with no new fact;
  2. a newsroom item: Broadcom has released fixed vCenter builds;
  3. a how-to diary that mentions CVE-2026-129448 only as an example;
  4. one new event from three feeds, one of them tier 1;
  5. an unrelated new story.

  Expected in all 3 runs: the vCenter story appears once, as an update of type `patch` with `since` 2026-11-21; candidate 1 is not an entry of its own; candidate 3 is not linked to a sent story; candidate 4 is one entry cited to the tier 1 feed. If a run misses: set triage to `llm.SONNET` and repeat. Put the three outcomes in the PR.

Check

```sh
python -m pytest -q
# on the VPS: a scratch clone of the branch, with a copy of the live clone's data/ in it and the variables of its .env loaded
python -m brief.run --dry-run | grep -E "repeat of|judged a different story|Update:"
```

**Order.** T1 and T2 in parallel, then T3. With two workers: about 4.5 hours of wall-clock time (estimate).

**Model input after T3 (estimate):** triage 15-25k tokens in (5.6k today), write +1-2k, critique +3-6k. All through the subscription CLI, so no bill per call.

## 8. Owner decisions and what is cut

The default applies unless the owner says otherwise. Each is one line to change.

| # | Decision | Default | Alternative |
|---|---|---|---|
| D1 | DNSC's rank | **Tier 2.** Cited when it is the only source (Romanian campaigns). For world-wide flaws an English source is cited | Tier 1: the Romanian alert is cited whenever DNSC covers the event |
| D2 | Kaspersky Securelist | **In.** The analysis is among the best published. The critic already checks every attribution against the text | Out: delete one line of `feeds.opml` |
| D3 | The Hacker News | **Radar, max 1 cited story per brief** | Remove it. The brief then misses research from vendors that are not on the list until a newsroom picks it up |
| D4 | Memory length, updates per brief | **14 days, max 2 updates** | Two constants |

Cut on purpose:

| Cut | Add back when |
|---|---|
| Fetching the full article text | The critic drops more than 1 item a day, or any update, for thin source text. Same trigger as `PLAN.md` 3.6. This is the next lever: 6 of the 18 sources still give under 250 characters |
| Embeddings or a vector store | Never at this size: 50 to 60 stories in memory |
| A catch-up window per feed (state for each feed) | A first-hand feed fails on more than 2 days a week |
| NVD, CVE.org or EPSS lookups | The reader wants a CVSS or EPSS number in the brief |
| EUVD as a second exploited-flaws list | KEV misses an exploited flaw that mattered in the EU |
| A proxy or VPN to reach `cisa.gov` | Never. If the pipeline moves to a network CISA accepts, re-add `https://www.cisa.gov/cybersecurity-advisories/all.xml` (it is the feed CISA's subscribe page lists) |

## 9. How we know it worked

All of it can be read from `logs/` and `data/digests/` on the VPS.

| Question | Measure | Target |
|---|---|---|
| Are the sources reachable? | Rows OK in the daily health table | At least 16 of 18 on 6 days of 7 |
| Is the mix better? | Per week: sent stories by tier of their `feed` | No brief of 4 or 5 stories with 2 cited to The Hacker News (enforced by code). At least a third of the week's stories cited to tier 1 |
| Do repeats still get through? | Critic drops with `repeat of` (each one is a triage miss) and the owner's own reading | 0 repeats reach the brief in two weeks. More than 1 critic catch a week: move triage to Sonnet |
| Are updates real? | The owner reads each "What's new" line for two weeks | 0 lines that are not new or not true |
| Are new stories lost? | `[triage] … repeat of` lines, read against that day's brief, in the first two weeks | 0 wrong skips |

**What this plan could not measure:** the VPS has one day of history (the pipeline went live on 2026-11-21), so feed reliability over weeks is unknown. The health table will show it.
