from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "skills/weekly-literature-crawl/scripts/weekly_literature_crawl.py"


def load_wrapper():
    spec = importlib.util.spec_from_file_location("weekly_literature_crawl", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    for name in ("run_weekly.py", "run_summary.py", "prepare_endnote_import.py"):
        (project / name).write_text("", encoding="utf-8")
    library = project / "library"
    categories = project / "categories"
    archive = project / "archive"
    library.mkdir()
    categories.mkdir()
    archive.mkdir()
    config = project / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "keywords": ["energy"],
                "paths": {
                    "library_root": str(library),
                    "category_source": str(categories),
                    "archive_root": str(archive),
                },
                "llm": {"api_key_env": "TEST_LLM_API_KEY"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return project, config


def test_check_validates_project_without_subprocess(tmp_path: Path, capsys) -> None:
    wrapper = load_wrapper()
    project, config = make_project(tmp_path)

    result = wrapper.main(
        ["--project-root", str(project), "--config", str(config), "check"]
    )

    assert result == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_dry_run_forwards_arguments_without_shell(tmp_path: Path, monkeypatch) -> None:
    wrapper = load_wrapper()
    project, config = make_project(tmp_path)
    captured = {}

    def run(command, *, cwd, check):
        captured.update(command=command, cwd=cwd, check=check)
        return type("Result", (), {"returncode": 7})()

    monkeypatch.setattr(wrapper.subprocess, "run", run)
    result = wrapper.main(
        [
            "--project-root",
            str(project),
            "--config",
            str(config),
            "--python",
            "test-python",
            "dry-run",
            "--limit",
            "4",
            "--headless",
            "true",
        ]
    )

    assert result == 7
    assert captured["command"] == [
        "test-python",
        str(project / "run_weekly.py"),
        "--config",
        str(config),
        "--dry-run",
        "--limit",
        "4",
        "--headless",
        "true",
    ]
    assert captured["cwd"] == project
    assert captured["check"] is False


def test_live_crawl_requires_confirmation(tmp_path: Path, capsys) -> None:
    wrapper = load_wrapper()
    project, config = make_project(tmp_path)

    result = wrapper.main(
        ["--project-root", str(project), "--config", str(config), "crawl"]
    )

    assert result == 2
    assert "--confirm-download" in capsys.readouterr().err


def test_summary_requires_configured_api_key(tmp_path: Path, monkeypatch, capsys) -> None:
    wrapper = load_wrapper()
    project, config = make_project(tmp_path)
    monkeypatch.delenv("TEST_LLM_API_KEY", raising=False)

    result = wrapper.main(
        ["--project-root", str(project), "--config", str(config), "summary"]
    )

    assert result == 2
    assert "TEST_LLM_API_KEY" in capsys.readouterr().err


def test_environment_project_discovery(tmp_path: Path, monkeypatch) -> None:
    wrapper = load_wrapper()
    project, _ = make_project(tmp_path)
    monkeypatch.setenv(wrapper.PROJECT_ENV, str(project))

    assert wrapper.resolve_project_root() == project.resolve()


def test_endnote_full_export_command(tmp_path: Path) -> None:
    wrapper = load_wrapper()
    project, config = make_project(tmp_path)
    args = wrapper.build_parser().parse_args(
        [
            "--project-root",
            str(project),
            "--config",
            str(config),
            "endnote",
            "--all",
            "--group",
            "Weekly",
        ]
    )

    command = wrapper.build_command(args, project, config)

    assert command[-3:] == ["--all", "--group", "Weekly"]


def test_config_validation_rejects_missing_paths(tmp_path: Path) -> None:
    wrapper = load_wrapper()
    config = tmp_path / "config.yaml"
    config.write_text("keywords:\n  - energy\npaths: {}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing paths"):
        wrapper.validate_config(config)


def test_config_validation_rejects_missing_directories(tmp_path: Path) -> None:
    wrapper = load_wrapper()
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "keywords": ["energy"],
                "paths": {
                    "library_root": "./missing-library",
                    "category_source": "./missing-categories",
                    "archive_root": "./missing-archive",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="directories do not exist"):
        wrapper.validate_config(config)
