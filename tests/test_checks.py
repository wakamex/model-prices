from datetime import datetime, timezone
from pathlib import Path

import pytest

from llm_prices import checks, main
from llm_prices.checks import Observed

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
# Official pricing pages as fetched on 2026-09-30.
PAGES = {
    "anthropic": (FIXTURES / "anthropic.md").read_text(),
    "deepseek": (FIXTURES / "deepseek.html").read_text(),
    "deepseek:zh": (FIXTURES / "deepseek-zh.html").read_text(),
    "google": (FIXTURES / "google.md").read_text(),
    "openai": (FIXTURES / "openai.md").read_text(),
    "xai": (FIXTURES / "xai.md").read_text(),
    "zai": (FIXTURES / "zai.md").read_text(),
}


def _prices(provider):
    return {(item.model, item.field, item.above, item.at): item.value
            for item in checks.SOURCES[provider][1](PAGES[provider], TODAY)}


def test_parsers_read_official_tables():
    anthropic = _prices("anthropic")
    assert anthropic[("claude-opus-5-5", "input", None, None)] == 4
    assert anthropic[("claude-opus-5-5", "cache_write", None, None)] == 5
    assert anthropic[("claude-opus-5-5", "cache_read", None, None)] == 0.2

    openai = _prices("openai")
    assert openai[("gpt-6-astra", "output", 272_000, None)] == 75
    assert ("gpt-5.4-mini", "input", 272_000, None) not in openai

    assert _prices("zai")[("GLM-5.3", "cache_read", None, None)] == 0.26

    xai = _prices("xai")
    assert xai[("grok-4.6", "input", None, None)] == 2
    assert xai[("grok-4.6", "output", 200_000, None)] == 12

    google = _prices("google")
    assert google[("Gemini 3.8 Flash", "input", None, None)] == 0.75
    assert google[("Gemini 2.5 Pro", "input", 200_000, None)] == 2.5
    assert google[("Gemini 2.5 Flash", "cache_read", None, None)] == 0.03
    assert ("Gemini 3.8 Flash", "cache_read", None, None) in google
    assert 0.5 not in {value for (model, field, _, _), value in google.items()
                       if model == "Gemini 3.8 Flash" and field == "cache_read"}

    deepseek = _prices("deepseek")
    assert sorted(value for (model, field, _, _), value in deepseek.items()
                  if model == "deepseek-flash" and field == "input") == [0.15, 0.3]


def test_google_dated_prices_follow_the_check_date():
    cell = "$0.75 through December 31, 2026. $1.50 starting January 1, 2027."

    assert checks._google_price(cell, TODAY) == [(0.75, None)]
    assert checks._google_price(cell, datetime(2027, 1, 2, tzinfo=timezone.utc)) == [(1.5, None)]


def test_official_pages_match_effective_prices():
    results = checks.run(pages=PAGES, today=TODAY)
    statuses = {result.status for result in results}

    assert "mismatch" not in statuses
    corrected = {(r.model, r.field) for r in results if r.status == "corrected"}
    assert ("deepseek/deepseek-v4-pro", "input") in corrected
    assert ("google/gemini-omni-flash-preview", "output") in corrected


def test_compare_flags_prices_that_differ():
    wrong = Observed("anthropic", "claude-opus-5-5", "input", 3.0)
    unknown = Observed("anthropic", "claude-mythos-5-1", "input", 10.0)

    mismatch, untracked = checks.compare([wrong, unknown], TODAY)

    assert (mismatch.status, mismatch.effective) == ("mismatch", 4.0)
    assert untracked.status == "untracked"


def test_changed_page_format_fails_loudly():
    with pytest.raises(ValueError, match="page format changed"):
        checks.run(["zai"], today=TODAY, pages={"zai": "# Pricing\n"})


def test_check_command_exit_status(monkeypatch, capsys):
    monkeypatch.setattr(checks, "fetch", lambda url: PAGES["zai"])
    assert main(["check", "zai"]) == 0
    assert "0 mismatch" in capsys.readouterr().out

    monkeypatch.setattr(checks, "fetch", lambda url: PAGES["zai"].replace("\\$1.4", "\\$9.9"))
    assert main(["check", "zai"]) == 1


def _terms(pages):
    results = checks.run(["deepseek"], today=TODAY, pages=pages)
    return {result.field: result for result in results if result.field.startswith("peak_terms")}


def test_peak_hour_terms_must_match_in_both_languages():
    pages = {"deepseek": PAGES["deepseek"], "deepseek:zh": PAGES["deepseek:zh"]}
    assert {field: result.status for field, result in _terms(pages).items()} == {
        "peak_terms:en": "ok", "peak_terms:zh": "ok",
    }

    changed = {**pages, "deepseek:zh": pages["deepseek:zh"].replace("14:00 - 18:00", "14:00 - 19:00")}
    terms = _terms(changed)
    assert (terms["peak_terms:en"].status, terms["peak_terms:zh"].status) == ("ok", "mismatch")
    assert "14:00 - 19:00" in checks.report(checks.run(["deepseek"], today=TODAY, pages=changed))


def test_holiday_calendar_must_cover_the_coming_weeks():
    ok, = checks.check_calendars({"deepseek"}, TODAY)
    late, = checks.check_calendars({"deepseek"}, datetime(2026, 11, 30, tzinfo=timezone.utc))

    assert (ok.status, late.status) == ("ok", "mismatch")
    assert "add the next year's holidays" in checks.report([late])
    assert checks.check_calendars({"anthropic"}, TODAY) == []
