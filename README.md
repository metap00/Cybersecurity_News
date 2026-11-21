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

A systemd user timer on the owner's VPS (user `openclaw`), daily at **06:30 Europe/Bucharest**, all year (the timer follows the time zone, so summer time needs no change).

`.github/workflows/digest.yml` has no schedule any more. It stays for manual runs: Actions → Daily brief → Run workflow, dry run by default. Keep it on dry run: a real run there sends a second brief and commits its own `data/`, which then blocks the VPS's `git pull`.

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
