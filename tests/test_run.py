"""brief.run with every stage replaced by a fake module. No network, no files outside tmp_path."""
import sys
import types

import pytest

from brief import run

STAGES = ["collect", "triage", "write", "critique", "weekly", "deliver"]


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Fake stage modules. Returns (calls, codes, set_mode)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    calls, codes, mode = [], {}, {"value": "full"}

    for name in STAGES:
        def main(argv=None, name=name):
            argv = list(argv or [])
            key = f"{name} {argv[0]}" if name == "deliver" else name
            calls.append(key)
            if key == "deliver send" and "--dry-run" in argv:
                sys.stdout.reconfigure(encoding="utf-8")  # real stages do this
                print("🔴 Fake headline\nDone. One tap below ↓")
            return codes.get(key, 0)
        monkeypatch.setitem(sys.modules, f"brief.{name}", types.SimpleNamespace(main=main))

    state = types.SimpleNamespace(load=lambda: {"version": 1, "days": []},
                                  next_mode=lambda s, today: mode["value"])
    monkeypatch.setitem(sys.modules, "brief.state", state)
    return calls, codes, lambda m: mode.update(value=m)


def test_daily_call_order(fakes):
    calls, _, _ = fakes
    assert run.main(["--date", "2026-11-21"]) == 0
    assert calls == ["deliver sync", "collect", "triage", "write", "critique", "deliver send"]


def test_stops_at_first_failure_and_names_it(fakes, capsys):
    calls, codes, _ = fakes
    codes["triage"] = 1
    assert run.main(["--date", "2026-11-21"]) == 1
    assert calls == ["deliver sync", "collect", "triage"]
    assert "stage 'triage'" in capsys.readouterr().out


def test_crash_counts_as_failure(fakes, monkeypatch):
    calls, _, _ = fakes

    def boom(argv=None):
        raise RuntimeError("x")
    monkeypatch.setitem(sys.modules, "brief.write", types.SimpleNamespace(main=boom))
    assert run.main(["--date", "2026-11-21"]) == 1
    assert calls == ["deliver sync", "collect", "triage"]


def test_sunday_takes_weekly_branch(fakes):
    calls, _, set_mode = fakes
    set_mode("weekly")
    assert run.main(["--date", "2026-11-22"]) == 0
    assert calls == ["deliver sync", "weekly", "deliver send"]


def test_small_mode_reaches_critique():
    assert ("critique", ["--mode", "small", "--date", "2026-11-21"]) in run.plan("small", "2026-11-21", False)


def test_dry_run_skips_sync_and_passes_flag(fakes, monkeypatch, tmp_path):
    calls, _, _ = fakes
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert run.main(["--dry-run", "--date", "2026-11-21"]) == 0
    assert "deliver sync" not in calls
    assert calls[-1] == "deliver send"
    assert run.plan("full", "2026-11-21", True)[-1][1][-1] == "--dry-run"
    text = summary.read_text(encoding="utf-8")
    assert "🔴 Fake headline" in text and "no (dry run)" in text


def test_summary_counts_from_out_files(fakes, monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "candidates.json").write_text(
        '{"feeds": [{"ok": true}, {"ok": false}], "candidates": [{}, {}, {}]}', encoding="utf-8")
    (out / "ranked.json").write_text('{"shortlist": [{}, {}]}', encoding="utf-8")
    (out / "digest.json").write_text('{"mode": "full", "items": [{}]}', encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert run.main(["--date", "2026-11-21"]) == 0
    text = summary.read_text(encoding="utf-8")
    for row in ("| feeds OK | 1/2 |", "| candidates | 3 |", "| shortlisted | 2 |", "| passed | 1 (full) |", "| sent | yes |"):
        assert row in text
