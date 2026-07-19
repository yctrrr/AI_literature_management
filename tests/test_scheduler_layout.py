from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_SCRIPTS = ROOT / "skills/weekly-literature-crawl/scripts"


def test_duplicate_scheduler_alias_is_removed() -> None:
    assert not (ROOT / "scheduler.ps1").exists()


def test_root_schedulers_are_compatibility_wrappers() -> None:
    for name in ("scheduler_crawl_endnote.ps1", "scheduler_summary.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert all(part in text for part in ("skills", "weekly-literature-crawl", "scripts"))
        assert "Register-ScheduledTask" not in text
        assert "@PSBoundParameters" in text


def test_scheduler_implementations_live_in_weekly_skill() -> None:
    expected_entries = {
        "scheduler_crawl_endnote.ps1": "run_weekly.py",
        "scheduler_summary.ps1": "run_summary.py",
    }
    for name, entry_point in expected_entries.items():
        text = (SKILL_SCRIPTS / name).read_text(encoding="utf-8")
        assert "Register-ScheduledTask" in text
        assert "$env:AI_LITERATURE_PROJECT_ROOT" in text
        assert entry_point in text

    crawl = (SKILL_SCRIPTS / "scheduler_crawl_endnote.ps1").read_text(encoding="utf-8")
    assert "--no-summarize" in crawl
