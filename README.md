# 🛡 Cybersecurity News: the morning brief

A daily cybersecurity brief for one reader on the way to a junior SOC analyst role. Every morning Telegram brings **3 to 5 stories summarized in plain English, one new concept, the day's new words, 1 thing to do and 3 quiz questions**. About 600-700 words, readable without clicking anything: each story ends with a small optional source link. Answering the quiz is the proof it was read, and it shows up as a streak.

## Example

Message 1, the stories:

```text
🟠 One Outlook email can leak your Windows login hash
A crafted email makes Outlook connect to an attacker's server and send your Windows
login hash, with no click. A hash is a scrambled form of your password that can be
cracked or reused. Microsoft has a fix. Defenders block outbound SMB and patch Outlook.
🎯 T1187 Forced Authentication: the email makes Outlook log in to the attacker's server.
👤 (only when the source names a group) who they are, state or criminal, who they target
Why it matters to you: you use Outlook, and this technique is on your path.
Source: SecurityWeek
```

Message 2, the rest:

```text
💡 Today I learned: Patch Gap
(3 plain sentences: what it is, how attackers use it, how defenders stop it)

📖 Words of the day
• hash: a scrambled, fixed-length form of a password that can be cracked or reused.
• SMB: the Windows file-sharing protocol.

▶ Do now (1 min): ⋮ → Help → About Google Chrome → Relaunch
For: Chrome zero-day is being exploited

Done. Last quiz 2/3 · Last 7 days ✅✅⬜✅ · streak 2 · 3 quick questions below ↓
```

Then 3 native Telegram quiz polls (3-4 options each, the explanation shows after the tap): one on the top story, one on a word of the day or the Today I Learned concept, and one applied "you are the SOC analyst on shift, what do you do first?" question. A day counts as read when at least one is answered; the next brief shows the score. 🔴 do something · 🟠 on your path · 🟡 worth knowing. Glossary terms are never repeated within the last 50, Today I Learned concepts within the last 7 (kept in `data/state.json`; before the first send they come from the frozen `history.json`). A message over Telegram's 4096 characters is split between stories.

On Sundays a short recap replaces the brief, in the same plain style: read rate, the week's pattern in 2-3 sentences, one weekend read with what it is about, and up to 3 missed or wrong questions re-asked.

## How it runs

A systemd user timer on the owner's VPS (user `openclaw`), daily at **06:30 Europe/Bucharest**, all year (the timer follows the time zone, so summer time needs no change).

`.github/workflows/digest.yml` has no schedule any more. It stays for manual runs: Actions → Daily brief → Run workflow, dry run by default. Keep it on dry run: a real run there sends a second brief and commits its own `data/`, which then blocks the VPS's `git pull`.

```text
python -m brief.run
  0 sync      close yesterday's 3 polls, record the answers  code
  1 collect   10 feeds + CISA KEV → out/candidates.json      code
  2 triage    score against profile.md → out/ranked.json     claude-haiku-5-5
  3 write     draft the top 5 + glossary + TIL → out/draft.json  claude-sonnet-5-5
  4 critique  check every fact against the source, fix or drop,
              pick 3-5 (word budget) → out/digest.json       claude-opus-5-5
  5 send      2 messages + 3 quiz polls, save state          code
Sunday: sync → weekly (claude-sonnet-5-5) → send --weekly
```

State lives in `data/state.json` and `data/digests/` on the VPS, written by `brief/state.py` and never committed. A failed run sends one Telegram line naming the log file. The model stages run through the Claude Code CLI (`claude -p`) on the owner's Claude subscription, so there is no API key and no per-call bill.

## VPS setup

What is on the VPS:

| Path | What |
|---|---|
| `~/Cybersecurity_News` | clone of `main`; each run starts with `git pull --ff-only` |
| `~/venvs/cybernews` | plain venv (standard library only) |
| `claude` on `PATH` | Claude Code CLI, logged in with the owner's subscription |
| `~/Cybersecurity_News/.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLAUDE_CODE_OAUTH_TOKEN`; mode 600, gitignored |
| `~/.config/systemd/user/cybernews.{service,timer}` | the schedule |
| `~/Cybersecurity_News/logs/YYYY-MM-DD.log` | one log per day, kept 60 days |
| `~/Cybersecurity_News/data/` | state and sent digests |

The brief sends with the Telegram Bot API (`sendMessage`, `sendPoll`, `stopPoll`) and never calls `getUpdates`, so it can share a bot with another app that polls for updates.

Rebuild from scratch:

```sh
git clone https://github.com/metap00/Cybersecurity_News.git ~/Cybersecurity_News
python3 -m venv ~/venvs/cybernews
# write ~/Cybersecurity_News/.env (the three variables above), then: chmod 600 ~/Cybersecurity_News/.env
```

`~/.config/systemd/user/cybernews.service`:

```ini
[Unit]
Description=Cybersecurity News daily brief (~/Cybersecurity_News)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/Cybersecurity_News
EnvironmentFile=%h/Cybersecurity_News/.env
ExecStart=/bin/sh -c 'mkdir -p logs; log=logs/$(date +%%F).log; { git pull -q --ff-only || echo "git pull failed, running current code"; %h/venvs/cybernews/bin/python -m brief.run; } >> "$log" 2>&1 || { curl -sS -o /dev/null --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" --data-urlencode "text=Cybersecurity brief failed today, see ~/Cybersecurity_News/$log" "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"; exit 1; }; find logs -name "*.log" -mtime +60 -delete'
```

`~/.config/systemd/user/cybernews.timer`:

```ini
[Unit]
Description=Cybersecurity News brief at 06:30 Romania time

[Timer]
OnCalendar=*-*-* 06:30 Europe/Bucharest
Persistent=true

[Install]
WantedBy=timers.target
```

```sh
systemctl --user daemon-reload && systemctl --user enable --now cybernews.timer
systemctl --user list-timers cybernews.timer      # next run
systemctl --user start cybernews.service          # run now (real send)
tail -n 50 ~/Cybersecurity_News/logs/$(date +%F).log
```

The user needs lingering (`loginctl enable-linger openclaw`) so the timer runs while nobody is logged in.

Getting the values: `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (run it once on the VPS, sign in with the Claude subscription; the token lasts a year). Without it, `claude` uses its own login in `~/.claude`, which expires. A bot token from `@BotFather` (`/newbot`). The chat id: send "hi" to the bot, open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id` (skip this if another app already polls that bot; it would hide the update).

## Edit `profile.md`

It drives the ranking and the "you" line of every item. Two minutes:

- `i use`: your OS, browser, phone OS, mail, apps. A 🔴 item needs a match here.
- `now`: what you are studying. 🟠 items and quiz topics come from it.
- `skip`: what you never want to see.

The repo is public, so keep it generic.

## Run locally

Python 3.11+.

```sh
python -m pytest -q                       # all tests, no network
python -m brief.run --dry-run             # full pipeline, prints the brief, sends nothing
python -m brief.deliver send --dry-run --date 2026-11-21   # render out/digest.json only
```

The model stages need the `claude` CLI, logged in (or `CLAUDE_CODE_OAUTH_TOKEN` set). A real send needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. `out/` is scratch and not committed.

## The old archive

Until 2026-11-21 a Claude Code routine wrote a long HTML digest plus an email every day. Those stay frozen in place: `summaries/` (one page per day), `index.html` (the list, [on GitHub Pages](https://metap00.github.io/Cybersecurity_News/)) and `history.json`. Nothing writes to them any more. `PLAN.md` explains why the format changed.
