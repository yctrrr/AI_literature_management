from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from init_project import initialize_project
from src.config import load_config


def initialization_values(library: Path, categories: Path, archive: Path) -> dict:
    return {
        "library_root": str(library),
        "category_source": str(categories),
        "archive_root": str(archive),
        "browser_profile": "",
        "zotero_enabled": False,
        "zotero_allowed_root": "",
        "llm_provider": "openai-compatible",
        "llm_model": "test-model",
        "llm_base_url": "https://llm.example.test/v1",
        "llm_api_key_env": "TEST_LLM_API_KEY",
    }


def test_initialize_and_load_config(tmp_path: Path) -> None:
    library = tmp_path / "library"
    categories = tmp_path / "categories"
    archive = tmp_path / "archive"
    library.mkdir()
    (categories / "Energy").mkdir(parents=True)
    output = tmp_path / "config.yaml"
    template = Path(__file__).parents[1] / "config.example.yaml"

    initialize_project(
        output,
        initialization_values(library, categories, archive),
        template,
    )

    loaded = load_config(output)
    assert loaded.paths.library_root == library.resolve()
    assert loaded.paths.category_source == categories.resolve()
    assert loaded.paths.archive_root == archive.resolve()
    assert loaded.llm.api_key_env == "TEST_LLM_API_KEY"
    assert not loaded.zotero.enabled
    assert "secret" not in output.read_text(encoding="utf-8").lower()


def test_environment_path_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    raw = yaml.safe_load(
        (Path(__file__).parents[1] / "config.example.yaml").read_text(encoding="utf-8")
    )
    raw["paths"] = {
        "library_root": "./library",
        "category_source": "./categories",
        "archive_root": "./archive",
    }
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    override = tmp_path / "other-library"
    monkeypatch.setenv("AI_LITERATURE_LIBRARY_ROOT", str(override))

    loaded = load_config(config_path)
    assert loaded.paths.library_root == override.resolve()
    assert loaded.paths.category_source == (tmp_path / "categories").resolve()


def test_initializer_rejects_overlapping_category_and_archive(tmp_path: Path) -> None:
    library = tmp_path / "library"
    categories = tmp_path / "categories"
    library.mkdir()
    categories.mkdir()
    values = initialization_values(library, categories, categories / "archive")
    with pytest.raises(ValueError, match="must not contain"):
        initialize_project(
            tmp_path / "config.yaml",
            values,
            Path(__file__).parents[1] / "config.example.yaml",
        )


def test_missing_config_points_to_initializer(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="init_project.py"):
        load_config(tmp_path / "missing.yaml")
