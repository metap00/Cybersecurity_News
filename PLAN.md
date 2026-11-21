# PLAN: the 60-second brief

Redesign of the Cybersecurity News agent around one goal: **the brief gets read.**

- **Reader:** one person moving into a junior SOC analyst role, with a small daily attention budget. So the output is short, scannable, action first, in small doses, with visible progress.
- **Status:** plan only. Nothing below is built yet.
- **Workers:** start at [section 5](#5-implementation-4-tasks). Contracts are in [section 8](#8-contracts).

## 1. Before and after

| | Today | After |
|---|---|---|
| What arrives | Email: 7 stories, 605 words, "~9 min read" (medians), plus a 2,900-word web page | One phone message: max 3 items, max 120 words |
| When | 03:45 UTC (05:45 local in winter) | 05:17 UTC (07:17 local in winter) |
| What it asks for | Nothing | 1 action of 1–2 minutes, 1 tap on a quiz |
| Knows if it was read | No | Yes. The quiz tap is recorded and shown as a streak |
| Empty sends | 36 of 116 | None |
| Built as | 1 agent, 1 prompt of 16 KB | 5 small stages, 3 Claude models, a check on each |
| Runs on | Claude Code cloud routine, plus GitHub Actions for the mail | GitHub Actions only. API cost about $3–4 a month (estimate) |

Needed from the owner before go-live, about 10 minutes: [section 6](#6-owner-setup-and-decisions).

## 2. Diagnosis: why it goes unread

Delivery is not the problem. The mail workflow succeeded in 99 of its last 99 runs. The email arrives and gets skipped.

| # | Cause | Evidence in this repo |
|---|---|---|
| 1 | **Too long for a daily habit** | Story-day emails: median 605 words and 7 stories. The banner itself announces "~9 min read" (median; never under 5, up to 18). The linked page: median 2,941 words. |
| 2 | **The useful part is hidden** | The page keeps every block in a closed `<details>` (rule in `CLAUDE.md`: "NO `open` attribute"), median 12 per page. The beginner explanation is 3 clicks from the inbox. The email template has no learning content. |
| 3 | **Not about the reader** | `CLAUDE.md` (304 lines) never describes the reader. Ranking is global severity. Actions are written for enterprise admins: "block outbound SMB (port 445) at the network perimeter" (2026-11-19). |
| 4 | **Reading changes nothing** | No single action, no question, no way to answer. `history.json` records what was sent, never what was read. |
| 5 | **A third of the sends are empty** | 36 of 116 emails carry 0 stories; 31 of them say the feeds were unreachable. In the last 25 days: 15 empty. They still go out, under a green "QUIET" banner. |
| 6 | **The alarm never changes** | Every story day is "ELEVATED": 55 of 55. ACTIVE and MODERATE have never been used. |
| 7 | **Same subject, bad hour** | The subject is always `Cybersecurity News — <date>` (`send-digest.yml:40`). In the last 30 days it landed at 03:40–03:56 UTC, hours before the reader is up. |
| 8 | **Not reliable at a glance** | 37 of 624 story links (5.9%) open a feed URL or a homepage. 227 (36%) go to 107 sites that are not in `feeds.opml`. "NTLM Relay Attack" was Today-I-Learned three times in six days (Nov 13, 16, 18) despite the no-repeat rule. |
| 9 | **One prompt does everything** | One agent fetches, ranks, writes, renders 3 HTML files, keeps state and pushes, with no check between steps. 4 of the 10 feed URLs fail a plain GET (2 × 404, 1 × 500, 1 × 403). |

Measured on 2026-11-21 from `summaries/`, `history.json`, `git log`, the Actions run list, and one GET per feed.

## 3. Redesign: "3-1-1"

**3 things to know, 1 thing to do, 1 question to answer.** One phone message. Nothing behind a click.

### 3.1 The daily brief

Example. Content adapted from this repo's 2026-11-19 digest. "You run Chrome" assumes the profile says so.

```text
🔴 Chrome zero-day is being exploited
You run Chrome, so this one is yours.
▶ Do now (1 min): ⋮ → Help → About Google Chrome → Relaunch
The Hacker News ↗

🟠 One Outlook email can leak your Windows login hash
SOC view: this is forced authentication, a technique on your path.
SecurityWeek ↗ · T1187 ↗

🟡 Check Point firewall bug exploited at about 24 customers
Path: privilege escalation, a limited login became root.
Bleeping Computer ↗

Done. Last 7 days ✅✅⬜✅ · streak 2 · one tap below ↓
```

Then, as a native Telegram quiz (sent silently, so the phone buzzes once):

```text
❓ An email made Outlook send your password hash to an attacker's server,
   with no click. What is this technique called?
   ○ Phishing (T1566)
   ○ Forced Authentication (T1187)
   ○ Brute Force (T1110)
```

One tap shows right or wrong at once, with a one-line explanation. That tap is the proof of read.

The first line is the top headline, so the lock-screen preview shows content, not a title. The example counts 92 words under the rule below (emoji and arrows count too): about 30 seconds of reading.

### 3.2 Rules, enforced by code

A brief that breaks a rule is not sent.

| Part | Limit |
|---|---|
| Items | max 3 (1 in small mode) |
| Whole message | max 120 words (whitespace-separated tokens of the visible text) |
| Headline | max 10 words, plain words |
| "You" line | max 12 words, must name something from `profile.md` |
| Action | exactly 1 per brief, max 14 words, takes 1–2 minutes, starts with a verb |
| Question | max 30 words, 3 options of max 6 words, explanation max 200 characters |
| Links | 1 article link per item, always the feed's own URL, attached by code. Optional ATT&CK link, built by code from the technique ID |
| Markers | 🔴 do something · 🟠 on your path · 🟡 worth knowing. No other labels, no threat level |

### 3.3 The loop

| Rule | Detail |
|---|---|
| A day counts | when the quiz is answered, right or wrong |
| Dots | last 7 days: ✅ answered, ⬜ sent but not answered, ➖ no quiz that day (failed run, nothing passed, or Sunday) |
| Streak | consecutive ✅ days. ➖ days do not break it |
| Small mode | the last 2 sent days are both ⬜ → 1 item only, until the next answer |
| No backlog | old briefs are never re-sent. Yesterday's question closes when today's brief goes out |
| Quiet day | no item passes the checks → the question only, from the reader's learning path |
| Failure | the pipeline fails → one honest line with a link to the run. Never a fake "quiet" |

### 3.4 Sunday: the recap

Replaces the daily brief on Sundays. Max 100 words.

```text
📅 Your week: read 5 of 6 · 4 of 5 right · streak 3
Pattern: three top stories were the same move, exploiting an app that faces the internet (T1190).
Weekend pick (15 min): Krebs on Security ↗ one line on why it is worth the time.
Two questions you missed come next ↓
```

Followed by up to 2 quiz questions from the week that were missed or answered wrong. Each is re-asked once.

### 3.5 Each cause gets one fix

| Cause | Fix |
|---|---|
| 1 Too long | Hard caps: 3 items, 120 words |
| 2 Hidden | The message is the whole brief |
| 3 Not about the reader | `profile.md` drives the ranking. Every item has a "you" line |
| 4 Reading changes nothing | 1 action, 1 question. The answer is recorded and shown |
| 5 Empty sends | Code fetches the feeds and reports each one. No empty messages |
| 6 Alarm never changes | No threat level. Three fixed markers |
| 7 Subject and hour | Phone push around 07:20. First line is the top headline |
| 8 Not reliable | Models never write a URL. A critic checks every claim against the feed text. State is kept by code |
| 9 One prompt | 5 small stages, JSON hand-offs, a check after each |

### 3.6 Cut on purpose

| Cut | Add back when |
|---|---|
| Daily email, daily HTML page, `index.html` updates | Never. `summaries/`, `index.html`, `history.json` stay as a frozen archive |
| Threat level, glossary, Today-I-Learned, threat-actor cards | The question and the Sunday recap cover the learning part |
| Fetching full article text | The critic drops more than 1 item a day for thin source text |
| Writer ↔ critic revision loop | Fewer than 3 items survive on most days |
| Auto-sync with `cybersecurity-journey` | That repo is updated again (last push 2026-06-15). Until then `profile.md` is edited by hand |
| Feedback buttons, free-text replies, a progress web page | The answer rate is steady and something is still missing |
| Batch API, prompt caching | Never at this size: one small run a day |

## 4. Pipeline

One GitHub Actions run a day. Three stages are Claude agents, and a fourth writes the Sunday recap. Fetching and sending are plain code: free, testable, and unable to invent a link. The 36 empty days came from an agent doing a fetch job.

```text
05:17 UTC  .github/workflows/digest.yml  →  python -m brief.run
  0 sync      close yesterday's quiz, record the answer      code
  1 collect   10 feeds + CISA KEV → candidates.json          code
  2 triage    score against profile.md → ranked.json         claude-haiku-5-5
  3 write     draft the top 5 → draft.json                   claude-sonnet-5-5
  4 critique  check, fix or drop, pick 3 → digest.json       claude-opus-5-5
  5 send      message + quiz to Telegram, save state         code
  commit data/ (state.json + digests/DATE.json)              GITHUB_TOKEN
Sunday: 0 sync → weekly (claude-sonnet-5-5) → send --weekly
```

| Stage | Model | What it does | Why this model |
|---|---|---|---|
| collect | none | Fetches feeds since the last send. Parses RSS and Atom. Merges duplicates (same URL, same CVE, similar title). Drops anything sent in the last 14 days. Flags CVEs listed in CISA KEV | A fetch is deterministic work |
| triage | `claude-haiku-5-5` | Scores each candidate 0–10 against `profile.md`. Labels it `act`, `learn`, `know` or `skip`. Code keeps the top 5 with score ≥ 6 | Volume: about 45 items a day, cheapest tokens |
| write | `claude-sonnet-5-5` | Drafts all 5: headline, "you" line, one action, one quiz question | Tight wording under hard caps |
| critique | `claude-opus-5-5` | Checks each draft against the feed text and the rules. Verdict per item: pass, fixed, or drop. Code then picks the top 3 | Judgment. It reads about 4k tokens a day, so the strongest checker costs cents. A wrong quiz answer teaches the wrong thing |
| send | none | Renders, re-checks the word cap, sends message and quiz, writes state | Sending is deterministic work |
| weekly | `claude-sonnet-5-5` | Names the week's pattern, chooses the weekend pick | One short text a week |

**No loops.** The writer over-produces (5 drafts for 3 slots), the critic vetoes, code selects. Three model calls a day, always.

**Hand-off.** Each stage reads one JSON file and writes the next ([section 8](#8-contracts)). A stage can be run and tested alone from a fixture file.

**Guardrails**

1. Models never output a URL. Code attaches the link from the collector's record. ATT&CK links are built by code from an ID that matches `^T\d{4}(\.\d{3})?$`.
2. Feed text is untrusted input. The model stages have no tools, return schema-constrained JSON, and all model text is HTML-escaped before sending.
3. Caps are checked in code after `write`, after `critique`, and again at `send`.
4. `data/state.json` is written by code only. No model maintains state.
5. A model refusal is handled (security news can trip the `cyber` classifier): see T2.
6. Secrets come from the environment and are never printed. The repo and its Action logs are public.

**Cost per day (estimate, to be replaced by logged token counts after the first run)**

| Stage | Tokens in / out | Cost |
|---|---|---|
| triage, Haiku 5.5 ($0.10 / $0.50 per MTok) | 8k / 3k | $0.002 |
| write, Sonnet 5.5 ($2 / $10) | 3k / 3k | $0.04 |
| critique, Opus 5.5 ($4 / $20) | 4k / 3k | $0.08 |
| **Day** | | **about $0.12** |

About $3–4 a month, Sunday recap included.

## 5. Implementation: 4 tasks

Four workers, in parallel, no shared files.

> **Read first.** `CLAUDE.md` in this repo still holds the old routine's prompt. Do not follow its workflow and do not write to `summaries/`. T4 replaces it.

**Conventions for every task**

- Python ≥ 3.11, standard library only. The one exception is `anthropic` in T2.
- Each stage is a module with `main(argv=None) -> int`, run as `python -m brief.<name>`. Exit 0 = ok, 1 = stop the run.
- Do not create `brief/__init__.py`, `tests/__init__.py` or `conftest.py`. Nobody owns those files, and `python -m` and `python -m pytest` work without them. The package is called `brief` so that no installed package shadows it.
- Tests: `python -m pytest tests/test_<name>.py -q` from the repo root. No network in tests.
- Open every file with `encoding="utf-8"`. In `--dry-run`, call `sys.stdout.reconfigure(encoding="utf-8")` before printing emoji.
- `out/` is scratch. Never commit it.
- Touch only the files listed for your task. Need a change elsewhere, or a contract change? Tell the coordinator. Do not edit `PLAN.md`.
- The contracts in [section 8](#8-contracts) are fixed. Build against them with your own fixture files.

**File ownership**

| Task | Creates or edits | Deletes |
|---|---|---|
| T1 | `brief/collect.py`, `feeds.opml`, `tests/test_collect.py`, `tests/fixtures/collect/` | |
| T2 | `brief/llm.py`, `brief/triage.py`, `brief/write.py`, `brief/critique.py`, `brief/weekly.py`, `prompts/`, `profile.md`, `requirements.txt`, `tests/test_llm_stages.py`, `tests/fixtures/llm/` | |
| T3 | `brief/state.py`, `brief/deliver.py`, `tests/test_deliver.py`, `tests/fixtures/deliver/` | |
| T4 | `brief/run.py`, `.github/workflows/digest.yml`, `.gitignore`, `README.md`, `CLAUDE.md`, `tests/test_run.py` | `.github/workflows/send-digest.yml` |

Nobody touches `summaries/`, `index.html`, `history.json`.

### T1. Collector (no model). About 45 minutes

**Goal:** `python -m brief.collect` writes `out/candidates.json` from live feeds and never reports a fake quiet day.

Spec

- Fix 4 feed URLs in `feeds.opml`. Status as measured on 2026-11-21:

  | Feed | Now | Replace with | Result |
  |---|---|---|---|
  | SANS ISC | `isc.sans.edu/rssfeed_small.xml` → 404 | `https://isc.sans.edu/rssfeed.xml` | 200 |
  | Ars Technica | `feeds.arstechnica.com/arstechnica/security` → 404 | `https://arstechnica.com/security/feed/` | 200 |
  | Dark Reading | `darkreading.com/rss/all` → 500 | `https://www.darkreading.com/rss.xml` | 200 |
  | CISA | `cisa.gov/uscert/ncas/all.xml` → 403 | `https://www.cisa.gov/cybersecurity-advisories/all.xml` | 200 with a browser-like User-Agent, 403 with a generic one |

- Send one browser-like User-Agent for every feed. No name, email or repo in it.
- Window: `since` = `sent_at` of the last entry in `data/state.json` → `days` whose mode is not `weekly`. No state → now − 24 h. Never older than now − 72 h.
- Parse RSS 2.0 (`item`) and Atom (`entry`). Prefer full content when the feed has it. Strip HTML to plain text, collapse whitespace, cut at 1,200 characters.
- Per feed: 15 s timeout, 3 MB cap, one retry. A failing feed is recorded and skipped.
- Merge duplicates inside the run when any of these holds: same canonical URL (lowercase host, no query, no fragment, no trailing slash); a shared CVE ID; title similarity ≥ 0.85 (`difflib.SequenceMatcher`, lowercased). Keep the entry with the longest summary and list the other feeds in `also`.
- Keys: `cve-2026-12345` for each CVE, `u:<host><path>` for the canonical URL.
- Drop a candidate when one of its keys appears in `days[].keys` of the last 14 days.
- KEV flag: fetch `https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json` and set `kev: true` when a candidate's CVE is listed. If that fetch fails: warn, set `kev: false`, continue.
- IDs: `c01`, `c02`, … newest first.
- Print a per-feed health table. Exit 1 when fewer than 3 feeds answered. A real quiet day (feeds fine, nothing new) exits 0 with an empty list.

Done when

- `tests/test_collect.py` covers: RSS and Atom parsing; the window; each of the 3 merge rules; the 14-day drop; a dead feed does not stop the run; fewer than 3 feeds → exit 1.
- A live run reports at least 8 of 10 feeds OK and writes a file that matches the contract.

Check

```sh
python -m pytest tests/test_collect.py -q
python -m brief.collect
```

### T2. Model stages: triage, write, critique, weekly. About 90 minutes

**Goal:** from `out/candidates.json` to a rule-clean `out/digest.json` in three model calls, with no model-written URL anywhere.

**Load the `claude-api` skill before writing any call. Do not write the API from memory.** Facts read from it on 2026-11-21:

- Model IDs, exactly: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`. No date suffix.
- JSON output: `output_config={"format": {"type": "json_schema", "schema": {...}}}`, schema with `required` and `additionalProperties: false`. Or `client.messages.parse(output_format=<Pydantic model>)`.
- Depth: `output_config={"effort": ...}`. Start with `low` for triage, `medium` for write and critique.
- These return a 400 on at least one of the three models, so send none of them: `temperature`, `top_p`, `top_k`, `budget_tokens`, `thinking: {"type": "disabled"}`, a forced `tool_choice`, an assistant prefill.
- A refusal is HTTP 200 with `stop_reason == "refusal"`. Check it before reading `content`.
- Sonnet 5.5 and Opus 5.5 accept server-side fallback: `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`. Haiku 5.5 has none.
- `max_tokens=16000`, not streamed.

Spec

- `brief/llm.py`: one function, `call(model, system, user, schema, effort) -> dict`. Official `anthropic` SDK. Prints input and output tokens for each call. On refusal: Sonnet and Opus use the server-side fallback; a refused Haiku call is re-run once on `claude-sonnet-5-5`. Still refused → raise, and the stage exits 1.
- `brief/triage.py`: one call. Input: candidates (`id`, `title`, `summary`, `feed`, `also`, `cves`, `kev`), `profile.md`, and `days[].titles` of the last 14 days. Output per candidate: `score`, `kind`, `reason`. Code keeps the top 5 with score ≥ 6 and writes `out/ranked.json`. Empty candidates → empty shortlist, exit 0.
  - `act`: touches something on the profile's `i use` line and there is something to do. `learn`: matches a `now` topic or a `tools` entry on the profile. `know`: big event (several feeds, or `kev`). `skip`: vendor news, funding, opinion, conferences, minor bugs in software the reader does not run.
- `brief/write.py`: one call. Drafts every shortlisted item, plus one `review_question` taken from `profile.md` alone. Avoids the `days[].question.topic` values of the last 14 days. Writes `out/draft.json`.
- `brief/critique.py --mode full|small --date YYYY-MM-DD`: one call. Verdict per item: `pass`, `fixed` (with replacement text), or `drop`, each with a list of issues. Then code:
  1. applies fixes and re-checks the caps (a fix that breaks a cap is a drop);
  2. picks the first 3 passing items in rank order (1 in small mode);
  3. takes the action from the first picked `act` item that has one, else from the top item, else `null`;
  4. takes the question from the top picked item;
  5. copies `url`, `feed`, `keys` from the candidates by `id`, and lists up to 2 more passing items in `also`;
  6. writes `out/digest.json`. No passing item → `mode: "quiz_only"` with `review_question`. That one dropped too → `mode: "none"`.
- `brief/weekly.py --date YYYY-MM-DD`: one call. Input: the `data/digests/*.json` files of the 7 days before the date. The model returns `pattern` and the `date` + `id` of the pick. Code resolves the pick's `headline`, `url`, `feed`. Writes `out/weekly.json`. No digest files → no call, `pattern: null`, `pick: null`.
- Code validation after `write` and after `critique`: every cap from section 3.2; ids exist; exactly 3 options; `correct` in range; `attack_id` matches the regex or is null; no `http`, `www.` or `<` in any model string. On failure: one retry with the error list, then exit 1.
- `prompts/triage.md`, `write.md`, `critique.md`, `weekly.md` hold the system prompts. Writer and critic share these rules:
  1. Plain words a first-year analyst uses. No hype.
  2. Facts about the event come only from the item's `title` and `summary`. Background knowledge may explain a concept (a technique, a defence, a log source). It may not add facts about the event.
  3. The "you" line names something from `profile.md`: a device or app, a course module, a tool, or a technique on the path.
  4. The action is for one person, takes 1–2 minutes, starts with a verb. Allowed: check a version or a setting on your own device; read one named page (the source, or the ATT&CK page); write one line in your notes that answers a stated prompt. Never: run a command, install or download something, anything that needs a company network.
  5. The question tests the concept, never a detail (no CVE numbers, dates or counts). One option is clearly right, the other two are plausible. No "all of the above". Someone who read the brief can answer it.
  6. Critic only: the marked answer is correct and the explanation is true.
- `profile.md`: create it with this seed (taken from the public `cybersecurity-journey` repo). It is public, so keep it generic.

  ```markdown
  # Reader profile (edit me: 2 minutes)
  goal: junior SOC analyst (blue team)
  done: CompTIA Security+ SY0-701, TryHackMe Pre-Security
  now: LetsDefend SOC Analyst path (SOC fundamentals, Cyber Kill Chain, MITRE ATT&CK,
       phishing email analysis, detecting web attacks, malware analysis basics, EDR,
       SIEM and log management, incident response, threat intelligence);
       Splunk SPL; Azure fundamentals on the way to cloud security
  tools: Splunk, Wireshark, tcpdump, Nmap, Burp Suite, John the Ripper
  revisit: ports and protocols, DNS attacks, zero-trust roles
  i use: <OS>, <browser>, <phone OS>, <mail>, GitHub   <- owner fills this in
  skip: funding and vendor news, conferences, opinion pieces
  ```

- `requirements.txt`: `anthropic`, pinned to the version used in the live check.

Done when

- `tests/test_llm_stages.py` (with `llm.call` replaced by canned JSON) covers: an over-long headline is rejected; a model string containing a URL is rejected; `url` in `digest.json` equals the candidate's; 3 items picked in rank order, 1 in small mode; everything dropped → `quiz_only`; a refused triage call is re-run on Sonnet; `weekly` with no digest files makes no call.
- Live, with a real key: the three daily stages turn a real `out/candidates.json` into a valid `out/digest.json` and print tokens per stage. Report the real cost of that run.

Check

```sh
python -m pytest tests/test_llm_stages.py -q
python -m brief.triage && python -m brief.write && python -m brief.critique --mode full --date 2026-11-21
```

### T3. Delivery, state, streak. About 60 minutes

**Goal:** `out/digest.json` becomes one Telegram message plus one quiz, and yesterday's tap becomes a ✅.

Telegram facts (Bot API 10.4, read on 2026-11-21)

- `sendPoll` works in a private chat with the bot. Question 1–300 characters, option 1–100 characters.
- A quiz needs `type: "quiz"` and `correct_option_ids: [i]` (an array). `explanation` is max 200 characters.
- `stopPoll(chat_id, message_id)` returns the final `Poll`, with `total_voter_count` and `options[].voter_count`.
- Do not use `getUpdates`. Telegram keeps updates for 24 hours only, and a late run would lose the answer.

Spec

- `brief/state.py`: `load() -> dict` (no file → `{"version": 1, "days": []}`), `save(state)`, `next_mode(state, today) -> "weekly" | "small" | "full"`, `dots(state, today) -> str`, `streak(state) -> int`. Keep the last 90 days.
  - `next_mode`: Sunday with at least 1 brief sent in the last 7 days → `weekly`. The last 2 days that carried a quiz are both unanswered → `small`. Otherwise `full`.
  - Dots and streak: a day with mode `weekly` or `none`, or with no entry at all, is ➖ and never breaks the streak.
- `brief/deliver.py sync`: take the last day that has a `poll_message_id` and `answered: null`. Call `stopPoll`. Set `answered = total_voter_count > 0` and `correct = options[question.correct].voter_count > 0`. Save. If Telegram says the poll is already closed or gone: set `answered: false` and continue.
- `brief/deliver.py send --date YYYY-MM-DD`:
  1. refuse when `days` already has that date, unless `--force`;
  2. render the layout of section 3.1 as Telegram HTML, every model string escaped, link previews off. Marker by `kind`: `act` 🔴, `learn` 🟠, `know` 🟡. The action line goes under the item named in `action.item_id`. Source line: the feed name linked to `url`; when `attack_id` is set, add the ID linked to `https://attack.mitre.org/techniques/<ID, with "." replaced by "/">/`. Footer: dots and streak; on the first run, "Done. One tap below ↓";
  3. count words; more than 120 → exit 1, nothing sent;
  4. `sendMessage`, then `sendPoll` with `disable_notification: true`;
  5. append the day entry and save `data/state.json`; copy the digest to `data/digests/<date>.json`. Only after both sends succeeded.
  - `mode: "quiz_only"`: one line ("Nothing worth your minute today. One question:") and the quiz. `mode: "none"`: send nothing, still append a day entry.
- `brief/deliver.py send --weekly --date YYYY-MM-DD`: read `out/weekly.json` and state. Compute "read x of n" (n = days in the last 7 that carried a quiz) and "y of x right" from state, never from a model. Render max 100 words; leave out the pattern or the pick line when it is null. Send. Then re-ask up to 2 questions from the last 7 days that were unanswered or wrong and not yet re-asked, oldest first, and mark each `reasked: true`. Append a day entry with mode `weekly`.
- `--dry-run`: print the exact text and the quiz payload. No network, no writes, and never `stopPoll` (it closes the question for real).
- Telegram over `urllib.request`. Environment: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Never print the token, the chat id, or a URL that contains the token. On an error, print the method name and Telegram's `description` only.

Done when

- `tests/test_deliver.py` (HTTP faked) covers: the word cap; escaping of `<` and `&`; a second send for the same date is refused; dots and streak across ✅ ⬜ ➖; the small-mode rule; `sync` turns voter counts into `answered` and `correct`; dry-run does no network and no writes.
- Live, with the owner's bot: `send` delivers the message and the quiz. After one tap, `sync` records `answered: true` with the right `correct` value. This also proves `voter_count` is filled for a private-chat quiz (the docs say it "may be 0 if unknown"). If it is not filled, stop and tell the coordinator.

Check

```sh
python -m pytest tests/test_deliver.py -q
python -m brief.deliver send --dry-run --date 2026-11-21
```

### T4. Run, schedule, docs. About 45 minutes

**Goal:** one command and one workflow run the whole thing every morning, and a failure is visible.

Spec

- `brief/run.py [--dry-run] [--date YYYY-MM-DD]`. Date defaults to today in UTC. `# ponytail: UTC date equals the local date for a 05:17 UTC run; revisit if the send time moves near midnight.`
  - Order: `deliver sync` (skipped in dry-run) → `state.next_mode` → on `weekly`: `weekly` → `deliver send --weekly`. Otherwise: `collect` → `triage` → `write` → `critique --mode --date` → `deliver send --date`.
  - Stop at the first non-zero exit and print the stage name.
  - When `GITHUB_STEP_SUMMARY` is set, append: feeds OK, candidates, shortlisted, passed, sent, tokens. In dry-run, also the rendered brief.
  - It relies on these fixed interfaces: `collect.main`, `triage.main`, `write.main`, `critique.main`, `weekly.main`, `deliver.main`, `state.load()`, `state.next_mode(state, today)`.
- `.github/workflows/digest.yml`:
  - `on: schedule: cron: '17 5 * * *'` and `workflow_dispatch` with a boolean input `dry_run` (default true). A scheduled run is never a dry run.
  - `permissions: contents: write`. The repo default is read-only.
  - `concurrency: digest`.
  - Steps: checkout, Python 3.12, `pip install -r requirements.txt`, `python -m brief.run`, upload `out/` as an artifact (7 days), commit and push `data/` with the built-in token (`git pull --rebase` first; skip when nothing changed).
  - A last step with `if: failure()`: one Telegram line, "Digest pipeline failed today", plus the run URL.
  - Secrets: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Delete `.github/workflows/send-digest.yml`. This also takes the hardcoded mail address out of the tree.
- `.gitignore`: `out/`, `__pycache__/`, `.pytest_cache/`.
- `README.md`: rewrite. What it is, the example brief, setup (section 6), how to edit `profile.md`, how to run locally, where the old archive lives.
- `CLAUDE.md`: replace with a dev guide of at most 40 lines: layout, commands, and the rules (caps, no model URLs, state written by code only). Its first lines must say: "If you are a scheduled routine asked to produce the daily digest: stop. `.github/workflows/digest.yml` produces it now. Do nothing." The old routine reads this file as its prompt.

Done when

- `tests/test_run.py` (stages replaced by fakes) covers: the call order; stop on the first failure; Sunday takes the weekly branch; dry-run skips `sync`.
- After T1–T3 are merged:
  1. `python -m pytest -q` is green;
  2. `gh workflow run digest.yml -f dry_run=true` is green and the job summary shows a brief of at most 120 words;
  3. one real run delivers to Telegram and commits `data/`.

Check

```sh
python -m pytest tests/test_run.py -q
gh workflow run digest.yml -f dry_run=true && gh run watch
```

**Order.** T1, T2, T3: parallel, merge in any order. T4: parallel too. Its three last checks wait for the other three. With 4 workers: about 1.5 hours of wall-clock time (estimate), plus the owner's 10 minutes.

## 6. Owner setup and decisions

Workers cannot do these. About 10 minutes in total.

1. **Anthropic API key.** Create one in the Anthropic Console. Add it as repo secret `ANTHROPIC_API_KEY`.
2. **Telegram bot.** In Telegram, message `@BotFather`, send `/newbot`, copy the token into repo secret `TELEGRAM_BOT_TOKEN`. Send "hi" to the new bot. Open `https://api.telegram.org/bot<TOKEN>/getUpdates`, copy the `chat.id` number into repo secret `TELEGRAM_CHAT_ID`.
3. **`profile.md`.** Fill in the "i use" line.
4. **After the first real brief:** switch off the old Claude Code cloud routine and revoke the GitHub token stored in its prompt. Optional: delete the unused secrets `GMAIL_APP_PASSWORD` and `RESEND_API_KEY`.

Decisions. The default applies unless the owner says otherwise.

| # | Decision | Default | Alternative and its price |
|---|---|---|---|
| D1 | Channel | **Telegram**: phone push, native quiz with instant feedback, the answer is readable later with no server | Email. Works with the existing Gmail secret, but a tap cannot be recorded, so the streak could only count days sent. Changes T3 only |
| D2 | Send time | **05:17 UTC**, about 07:17 local in winter and 08:17 in summer | Any hour: one cron line |

D1 must be confirmed before T3 starts. T1 and T2 do not depend on it. T4 depends on it only for the failure notice and the secret names.

## 7. How we know it worked

- **Metric:** days answered ÷ days a brief was sent (6 a week, Monday to Saturday). Both are in `data/state.json`, and the Sunday recap prints them.
- **Target:** at least 4 of 6 in the second week.
- **Under 3 of 6 after two weeks:** change the channel or the hour first. Do not add features.

## 8. Contracts

Fixed. A change goes through the coordinator.

`out/candidates.json` (T1 → T2)

```jsonc
{
  "generated_at": "2026-11-21T05:17:40Z",
  "since": "2026-11-20T05:21:04Z",
  "feeds": [{"name": "Bleeping Computer", "ok": true, "items": 4, "error": null}],
  "candidates": [
    {
      "id": "c01",
      "title": "Google issues emergency Chrome update for exploited zero-day",
      "url": "https://thehackernews.com/2026/11/google-issues-chrome-security-update.html",
      "feed": "The Hacker News",
      "published": "2026-11-20T09:12:00Z",
      "summary": "plain text, max 1200 characters",
      "cves": ["CVE-2026-125350"],
      "kev": true,
      "also": ["Bleeping Computer"],
      "keys": ["cve-2026-125350", "u:thehackernews.com/2026/11/google-issues-chrome-security-update.html"]
    }
  ]
}
```

`out/ranked.json` (triage → write, inside T2)

```jsonc
{
  "shortlist": [   // max 5, best first, score >= 6; every candidate field is kept unchanged
    {"id": "c01", "score": 9, "kind": "act", "reason": "max 12 words"}
  ]
}
```

`out/draft.json` (write → critique, inside T2)

```jsonc
{
  "items": [   // one per shortlist entry, same order
    {
      "id": "c01",
      "headline": "Chrome zero-day is being exploited",
      "you": "You run Chrome, so this one is yours.",
      "action": {"text": "⋮ → Help → About Google Chrome → Relaunch", "minutes": 1},   // or null
      "attack_id": "T1203",                                                            // or null
      "question": {"text": "...", "options": ["...", "...", "..."], "correct": 1, "explanation": "...", "topic": "T1203"}
    }
  ],
  "review_question": {"text": "...", "options": ["...", "...", "..."], "correct": 0, "explanation": "...", "topic": "ports"}
}
```

`out/digest.json` (T2 → T3). After a send, T3 copies it to `data/digests/<date>.json`.

```jsonc
{
  "date": "2026-11-21",
  "mode": "full",   // full | small | quiz_only | none
  "items": [
    {
      "id": "c01", "kind": "act",
      "headline": "...", "you": "...", "attack_id": null,
      "url": "https://...",          // copied from the candidate by code
      "feed": "The Hacker News",     // copied
      "keys": ["cve-2026-125350"]    // copied
    }
  ],
  "action": {"item_id": "c01", "text": "...", "minutes": 1},   // or null
  "question": {"text": "...", "options": ["...", "...", "..."], "correct": 1, "explanation": "...", "topic": "T1187"},   // null when mode is none
  "also": [{"id": "c07", "headline": "...", "url": "https://...", "feed": "..."}]   // max 2, for the Sunday pick
}
```

`out/weekly.json` (T2 → T3)

```jsonc
{
  "date": "2026-11-22",
  "pattern": "max 40 words",
  "pick": {"headline": "...", "url": "https://...", "feed": "...", "why": "max 20 words"}   // url and feed resolved by code; or null
}
```

`data/state.json` (written by T3 only; T1 and T2 read it)

```jsonc
{
  "version": 1,
  "days": [   // oldest first, max 90
    {
      "date": "2026-11-21",
      "mode": "full",   // full | small | quiz_only | none | weekly
      "sent_at": "2026-11-21T05:21:04Z",
      "keys": ["cve-2026-125350", "u:thehackernews.com/2026/11/..."],   // T1 reads: last 14 days
      "titles": ["Chrome zero-day is being exploited"],                 // T2 reads: last 14 days
      "poll_message_id": 4711,   // null when no quiz was sent
      "question": {"text": "...", "options": ["...", "...", "..."], "correct": 1, "explanation": "...", "topic": "T1187"},   // T2 reads topic: last 14 days
      "answered": null,          // null until the next run's sync, then true or false
      "correct": null,
      "reasked": false
    }
  ]
}
```

Command lines

```text
python -m brief.collect
python -m brief.triage
python -m brief.write
python -m brief.critique --mode full|small --date YYYY-MM-DD
python -m brief.weekly   --date YYYY-MM-DD
python -m brief.deliver  sync
python -m brief.deliver  send [--weekly] [--dry-run] [--force] --date YYYY-MM-DD
python -m brief.run      [--dry-run] [--date YYYY-MM-DD]
```
