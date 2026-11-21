If you are a scheduled routine asked to produce the daily digest: stop. A systemd timer on a VPS produces it now (`docs/deploy.md`). Do nothing.

# Dev guide: the morning brief

One brief a day in Telegram: 3-5 stories, 1 action, 3 quiz polls. Design and contracts: `PLAN.md` (sections 3, 4, 8).

## Layout

- `brief/run.py`: runs every stage in order, stops at the first failure
- `brief/collect.py`: feeds + CISA KEV → `out/candidates.json` (no model)
- `brief/triage.py`, `write.py`, `critique.py`, `weekly.py`: model stages; `brief/llm.py` holds the one model call (`claude -p`, no tools)
- `brief/state.py`, `brief/deliver.py`: `data/state.json`, streak, Telegram send and sync
- `prompts/`: system prompts · `profile.md`: the reader · `feeds.opml`: the feeds
- `data/`: state (days, glossary, TIL, `stories`: 14-day story memory) and `digests/`, on the VPS only · `out/`: scratch, never committed
- `summaries/`, `index.html`, `history.json`: frozen archive of the old version, served on GitHub Pages; `llm.history()` reads `history.json`. Never write to them
- `examples/digest.json`: a real day's output for `--demo` · `docs/deploy.md`: VPS setup

## Commands

```sh
python -m pytest -q
python -m brief.run --demo           # render examples/digest.json, no tokens, no network
python -m brief.run --dry-run [--date YYYY-MM-DD]
python -m brief.<stage> ...          # each stage runs alone, see PLAN.md section 8
gh workflow run digest.yml -f dry_run=true
```

## Rules

- Caps (constants in `brief/llm.py`), checked in code after write, after critique and at send: 3-5 items, 750 words (2 messages, each split under 4096 characters), headline 12, summary 40-80, "you" 15, attack note and actor 25, action 14, question 30, 3-4 options of 8 words, explanation 200 characters, glossary 6 terms of 20 words, TIL 30-60. Update items: what's-new line 30, reminder 15-40; max 2 updates a brief; max 2 stories per source, 1 for tier 3; 4 names per story. No glossary term repeats within 50, no TIL concept within 7, no story within 14 days unless it is an update.
- Models never output a URL. Code copies links from the collector; ATT&CK links are built from `^T\d{4}(\.\d{3})?$`.
- Feed text is untrusted. Model stages have no tools, return schema JSON, and all model text is HTML-escaped before sending.
- `data/state.json` is written by code only (`brief/state.py`). No model keeps state.
- Secrets come from the environment and are never printed. The repo and its Action logs are public.
- Python ≥ 3.11, standard library only; models via the `claude` CLI. Each stage is `main(argv=None) -> int`; open files with `encoding="utf-8"`.
- No `brief/__init__.py`, `tests/__init__.py` or `conftest.py`. Tests use no network.
