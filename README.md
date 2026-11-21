# 🛡 Cybersecurity News: the 60-second brief

A daily cybersecurity brief for one reader on the way to a junior SOC analyst role. Every morning one Telegram message brings **3 things to know, 1 thing to do, 1 question to answer**. Max 120 words. Nothing behind a click. Answering the quiz is the proof it was read, and it shows up as a streak.

## Example

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

Then a native Telegram quiz with 3 options. 🔴 do something · 🟠 on your path · 🟡 worth knowing.

On Sundays a short recap replaces the brief: read rate, the week's pattern, one weekend read, and up to 2 missed questions re-asked.

## How it runs

One GitHub Actions workflow, `.github/workflows/digest.yml`, daily at **04:30 UTC**.

| Season | Arrives (Romania) |
|---|---|
| Winter (EET, UTC+2) | 06:30 |
| Summer (EEST, UTC+3) | 07:30, unless the cron is changed to `'30 3 * * *'` |

```text
python -m brief.run
  0 sync      close yesterday's quiz, record the answer      code
  1 collect   10 feeds + CISA KEV → out/candidates.json      code
  2 triage    score against profile.md → out/ranked.json     claude-haiku-5-5
  3 write     draft the top 5 → out/draft.json               claude-sonnet-5-5
  4 critique  check, fix or drop, pick 3 → out/digest.json   claude-opus-5-5
  5 send      message + quiz to Telegram, save state         code
Sunday: sync → weekly (claude-sonnet-5-5) → send --weekly
```

State lives in `data/state.json` and `data/digests/`, committed by the workflow. A failed run sends one Telegram line with a link to the run. API cost: about $3–4 a month (estimate).

## Setup (about 10 minutes)

1. **Anthropic API key.** Create one in the Anthropic Console. Add it as repo secret `ANTHROPIC_API_KEY`.
2. **Telegram bot.** Message `@BotFather`, send `/newbot`, put the token in repo secret `TELEGRAM_BOT_TOKEN`. Send "hi" to the new bot, open `https://api.telegram.org/bot<TOKEN>/getUpdates`, put the `chat.id` number in repo secret `TELEGRAM_CHAT_ID`.
3. **`profile.md`.** Fill in the `i use` line (see below).
4. **Test it.** Actions → Daily brief → Run workflow (dry run is on by default). The job summary shows the rendered brief.
5. **After the first real brief:** switch off the old Claude Code cloud routine and revoke the GitHub token in its prompt. Optional: delete the unused secrets `GMAIL_APP_PASSWORD` and `RESEND_API_KEY`.

## Edit `profile.md`

It drives the ranking and the "you" line of every item. Two minutes:

- `i use`: your OS, browser, phone OS, mail, apps. A 🔴 item needs a match here.
- `now`: what you are studying. 🟠 items and quiz topics come from it.
- `skip`: what you never want to see.

The repo is public, so keep it generic.

## Run locally

Python 3.11+.

```sh
pip install -r requirements.txt
python -m pytest -q                       # all tests, no network
python -m brief.run --dry-run             # full pipeline, prints the brief, sends nothing
python -m brief.deliver send --dry-run --date 2026-11-21   # render out/digest.json only
```

The model stages need `ANTHROPIC_API_KEY`. A real send needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. `out/` is scratch and not committed.

## The old archive

Until 2026-11-21 a Claude Code routine wrote a long HTML digest plus an email every day. Those stay frozen in place: `summaries/` (one page per day), `index.html` (the list, [on GitHub Pages](https://metap00.github.io/Cybersecurity_News/)) and `history.json`. Nothing writes to them any more. `PLAN.md` explains why the format changed.
