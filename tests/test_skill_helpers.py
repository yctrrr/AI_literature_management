from __future__ import annotations

import argparse
import importlib.util
import json
import os
import zipfile
from pathlib import Path

import pytest
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
    assert not list(tmp_path.glob(".plugin.xpi.*.tmp"))
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600


def test_zotero_plugin_tracks_existing_item_rollback() -> None:
    bootstrap = (
        ROOT
        / "skills/zotero-link-import/assets/zotero-plugin/bootstrap.js"
    ).read_text(encoding="utf-8")
    assert "rememberExistingItem" in bootstrap
    assert "collections: [...item.getCollections()]" in bootstrap
    assert "await rollback(createdIDs, modifiedItems)" in bootstrap


def test_zotero_installer_restores_config_and_profile_on_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    installer = load_module(
        "zotero_install_plugin_rollback",
        "skills/zotero-link-import/scripts/install_plugin.py",
    )
    allowed_root = tmp_path / "library"
    profile = tmp_path / "profile"
    extensions = profile / "extensions"
    allowed_root.mkdir()
    extensions.mkdir(parents=True)
    profiles_ini = tmp_path / "profiles.ini"
    profiles_ini.write_text(
        "[Profile0]\nName=default\nIsRelative=0\nPath=" + str(profile) + "\nDefault=1\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "client.json"
    config_path.write_bytes(b"old-config")
    destination = extensions / f"{installer.PLUGIN_ID}.xpi"
    destination.write_bytes(b"old-xpi")
    original_write = installer.atomic_private_write

    def fail_profile_write(path: Path, data: bytes) -> None:
        if path == destination:
            raise OSError("profile write failed")
        original_write(path, data)

    monkeypatch.setattr(installer, "atomic_private_write", fail_profile_write)
    monkeypatch.setattr(installer, "discover_zotero_exe", lambda _value: None)
    args = argparse.Namespace(
        allowed_root=str(allowed_root),
        config=config_path,
        profiles_ini=profiles_ini,
        zotero_exe=None,
        install_policy=False,
    )

    with pytest.raises(OSError, match="profile write failed"):
        installer.install(args)

    assert config_path.read_bytes() == b"old-config"
    assert destination.read_bytes() == b"old-xpi"
    assert not config_path.with_suffix(".xpi").exists()


def test_skill_packages_are_self_contained() -> None:
    expected = {
        "literature-ingest",
        "literature-locator",
        "weekly-literature-crawl",
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
