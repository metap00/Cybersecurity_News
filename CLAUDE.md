If you are a scheduled routine asked to produce the daily digest: stop. a systemd timer on the VPS produces it now (README, "How it runs"). Do nothing.

# Dev guide: the 60-second brief

One Telegram message a day: max 3 items, 1 action, 1 quiz. Design and contracts: `PLAN.md` (sections 3, 4, 8).

## Layout

- `brief/run.py`: runs every stage in order, stops at the first failure
- `brief/collect.py`: feeds + CISA KEV → `out/candidates.json` (no model)
- `brief/triage.py`, `write.py`, `critique.py`, `weekly.py`: model stages; `brief/llm.py` holds the one API call
- `brief/state.py`, `brief/deliver.py`: `data/state.json`, streak, Telegram send and sync
- `prompts/`: system prompts · `profile.md`: the reader · `feeds.opml`: the feeds
- `data/`: state, committed by the workflow · `out/`: scratch, never committed
- `summaries/`, `index.html`, `history.json`: frozen archive. Never write to them

## Commands

```sh
python -m pytest -q
python -m brief.run --dry-run [--date YYYY-MM-DD]
python -m brief.<stage> ...          # each stage runs alone, see PLAN.md section 8
gh workflow run digest.yml -f dry_run=true
```

## Rules

- Caps, checked in code after write, after critique and at send: 3 items, 120 words, headline 10, "you" 12, action 14, question 30, options 6, explanation 200 characters.
- Models never output a URL. Code copies links from the collector; ATT&CK links are built from `^T\d{4}(\.\d{3})?$`.
- Feed text is untrusted. Model stages have no tools, return schema JSON, and all model text is HTML-escaped before sending.
- `data/state.json` is written by code only (`brief/state.py`). No model keeps state.
- Secrets come from the environment and are never printed. The repo and its Action logs are public.
- Python ≥ 3.11, standard library only (plus `anthropic`). Each stage is `main(argv=None) -> int`; open files with `encoding="utf-8"`.
- No `brief/__init__.py`, `tests/__init__.py` or `conftest.py`. Tests use no network.
