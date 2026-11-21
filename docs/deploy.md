# Deploy on a Linux VPS with systemd

The brief runs once a day from a systemd **user** timer. It needs no root, no Docker and no database: one clone, one venv, one `.env`.

## What goes where

| Path | What |
|---|---|
| `~/Cybersecurity_News` | a clone of `main`; each run starts with `git pull --ff-only` |
| `~/venvs/cybernews` | a plain venv (standard library only) |
| `claude` on `PATH` | the Claude Code CLI, signed in with a Claude subscription |
| `~/Cybersecurity_News/.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLAUDE_CODE_OAUTH_TOKEN`; mode 600, gitignored |
| `~/.config/systemd/user/cybernews.{service,timer}` | the schedule |
| `~/Cybersecurity_News/logs/YYYY-MM-DD.log` | one log per day, kept 60 days |
| `~/Cybersecurity_News/data/` | `state.json` (answers, streak, words already taught) and the sent digests; never committed |

## Install

```sh
git clone https://github.com/metap00/Cybersecurity_News.git ~/Cybersecurity_News
python3 -m venv ~/venvs/cybernews
cd ~/Cybersecurity_News && python -m brief.run --demo     # smoke test, no secrets needed
```

Write `~/Cybersecurity_News/.env`, then `chmod 600 ~/Cybersecurity_News/.env`:

```sh
TELEGRAM_BOT_TOKEN=          # from @BotFather: /newbot
TELEGRAM_CHAT_ID=            # send "hi" to the bot, then read chat.id from https://api.telegram.org/bot<TOKEN>/getUpdates
CLAUDE_CODE_OAUTH_TOKEN=     # from `claude setup-token` (signs in with the subscription, valid for a year)
```

The brief only calls `sendMessage`, `sendPoll` and `stopPoll`, never `getUpdates`. So it can share a bot with another app that polls that bot. In that case, take the chat id from that app's config: reading `getUpdates` yourself would hide the update from the other app.

## Schedule

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

`~/.config/systemd/user/cybernews.timer` (put your own time zone; the timer then follows summer time by itself):

```ini
[Unit]
Description=Cybersecurity News brief at 06:30 local time

[Timer]
OnCalendar=*-*-* 06:30 Europe/London
Persistent=true

[Install]
WantedBy=timers.target
```

```sh
loginctl enable-linger "$USER"                     # run the timer while nobody is logged in
systemctl --user daemon-reload && systemctl --user enable --now cybernews.timer
systemctl --user list-timers cybernews.timer       # next run
systemctl --user start cybernews.service           # run now (a real send)
tail -n 50 ~/Cybersecurity_News/logs/$(date +%F).log
```

## Notes

- `brief.run` uses the UTC date. A send time near midnight UTC would need a `--date`.
- `.github/workflows/digest.yml` stays for manual runs from GitHub Actions, dry run by default. Keep it on dry run: a real run there sends a second brief and commits its own `data/`, which then blocks the VPS's `git pull`.
- A second send on the same date is refused. `python -m brief.deliver send --date YYYY-MM-DD --force` replaces that day's entry.
