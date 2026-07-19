from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ingest_and_locator_use_configured_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    library = tmp_path / "library"
    topic = library / "Energy"
    topic.mkdir(parents=True)
    main = topic / "2026 Example Urban Energy Study.pdf"
    supplement = topic / "Supp-2026 Example Urban Energy Study.csv"
    main.write_bytes(b"%PDF-test")
    supplement.write_text("value\n1\n", encoding="utf-8")
    monkeypatch.setenv("AI_LITERATURE_LIBRARY_ROOT", str(library))

    ingest = load_module(
        "literature_ingest_helper",
        "skills/literature-ingest/scripts/literature_ingest_helper.py",
    )
    locator = load_module(
        "locate_literature",
        "skills/literature-locator/scripts/locate_literature.py",
    )
    assert ingest.configured_root() == library.resolve()
    duplicates = ingest.duplicate_candidates(
        library,
        "Example Urban Energy Study",
        None,
        None,
    )
    assert duplicates and Path(duplicates[0]["path"]) == main
    assert locator.configured_root() == library.resolve()
    assert locator.is_attachment(supplement)
    assert locator.score("Urban Energy Study", main.stem) > 0.7


def test_zotero_plugin_build_injects_local_values(tmp_path: Path) -> None:
    installer = load_module(
        "zotero_install_plugin",
        "skills/zotero-link-import/scripts/install_plugin.py",
    )
    allowed_root = tmp_path / "library"
    allowed_root.mkdir()
    output = tmp_path / "plugin.xpi"
    installer.build_xpi("test-token-value", allowed_root, output)

    with zipfile.ZipFile(output) as archive:
        bootstrap = archive.read("bootstrap.js").decode("utf-8")
    assert "__INSTALL_TOKEN__" not in bootstrap
    assert "__ALLOWED_ROOT__" not in bootstrap
    assert "test-token-value" in bootstrap
    assert json.dumps(str(allowed_root)) in bootstrap


def test_skill_packages_are_self_contained() -> None:
    expected = {
        "literature-ingest",
        "literature-locator",
        "zotero-link-import",
        "zotero-docx-paper-writing",
    }
    skill_root = ROOT / "skills"
    assert {path.name for path in skill_root.iterdir() if path.is_dir()} == expected
    for name in expected:
        skill_file = skill_root / name / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == name
        assert metadata["description"]
        assert not (skill_root / name / "config.json").exists()
        assert not list((skill_root / name).rglob("*.xpi"))
