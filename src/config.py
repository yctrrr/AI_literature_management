from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


CONFIG_ENV = "AI_LITERATURE_CONFIG"
PATH_ENVIRONMENTS = {
    "library_root": "AI_LITERATURE_LIBRARY_ROOT",
    "category_source": "AI_LITERATURE_CATEGORY_SOURCE",
    "archive_root": "AI_LITERATURE_ARCHIVE_ROOT",
}


@dataclass(slots=True)
class NatureConfig:
    base_url: str = "https://www.nature.com"
    journals: list[str] = field(default_factory=lambda: [""])
    journal_name_required_term: str = "Nature"
    feed_first: bool = True
    feed_urls: list[str] = field(default_factory=list)
    search_fallback: bool = True
    min_results_before_search_fallback: int = 5
    search_max_pages_per_keyword: int = 2
    delay_seconds: int = 8
    request_timeout_seconds: int = 30
    user_agent: str = "AILiteratureManagement/1.0"


@dataclass(slots=True)
class PathsConfig:
    library_root: Path
    category_source: Path
    archive_root: Path


@dataclass(slots=True)
class DownloadConfig:
    require_pdf: bool = True
    first_attachment_only: bool = True
    skip_if_no_pdf: bool = True
    max_articles_per_run: int = 20


@dataclass(slots=True)
class BrowserConfig:
    headless: bool = True
    use_chrome_profile: bool = False
    user_data_dir: str = ""


@dataclass(slots=True)
class LLMConfig:
    provider: str = "openai-compatible"
    model: str = "your-model"
    api_key_env: str = "LLM_API_KEY"
    base_url: str = ""
    summarize_by_default: bool = False
    max_pdf_chars: int = 60000


@dataclass(slots=True)
class ZoteroConfig:
    enabled: bool = False
    allowed_root: Path | None = None


@dataclass(slots=True)
class AppConfig:
    keywords: list[str]
    nature: NatureConfig
    paths: PathsConfig
    download: DownloadConfig
    browser: BrowserConfig
    llm: LLMConfig
    zotero: ZoteroConfig
    project_root: Path
    config_path: Path


def default_config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV, "config.yaml")).expanduser()


def load_config(path: Path | None = None) -> AppConfig:
    path = (path or default_config_path()).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration not found: {path}. Run 'python init_project.py' first."
        )
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    config_dir = path.parent
    paths_raw = raw.get("paths") or {}
    required_paths = ("library_root", "category_source", "archive_root")
    missing_paths = [key for key in required_paths if not paths_raw.get(key)]
    if missing_paths:
        raise ValueError(
            "config.yaml is missing path settings: " + ", ".join(missing_paths)
        )

    paths = PathsConfig(
        **{
            key: _resolve_path(
                config_dir,
                os.environ.get(PATH_ENVIRONMENTS[key]) or str(paths_raw[key]),
            )
            for key in required_paths
        }
    )

    browser_raw = dict(raw.get("browser") or {})
    browser_profile = os.environ.get("AI_LITERATURE_BROWSER_PROFILE")
    if browser_profile is not None:
        browser_raw["user_data_dir"] = browser_profile
        browser_raw["use_chrome_profile"] = bool(browser_profile)
    if browser_raw.get("user_data_dir"):
        browser_raw["user_data_dir"] = str(
            _resolve_path(config_dir, str(browser_raw["user_data_dir"]))
        )

    zotero_raw = dict(raw.get("zotero") or {})
    zotero_root = os.environ.get("ZOTERO_LINK_ALLOWED_ROOT")
    if zotero_root is not None:
        zotero_raw["allowed_root"] = zotero_root
    allowed_root = zotero_raw.get("allowed_root")
    zotero = ZoteroConfig(
        enabled=bool(zotero_raw.get("enabled", False)),
        allowed_root=_resolve_path(config_dir, str(allowed_root)) if allowed_root else None,
    )
    if zotero.enabled and zotero.allowed_root is None:
        raise ValueError("zotero.allowed_root is required when Zotero is enabled")

    llm = LLMConfig(**(raw.get("llm") or {}))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", llm.api_key_env):
        raise ValueError(f"Invalid LLM API key environment variable name: {llm.api_key_env}")

    keywords = [str(value).strip() for value in (raw.get("keywords") or []) if str(value).strip()]
    if not keywords:
        raise ValueError("config.yaml must define at least one keyword")

    return AppConfig(
        keywords=keywords,
        nature=NatureConfig(**(raw.get("nature") or {})),
        paths=paths,
        download=DownloadConfig(**(raw.get("download") or {})),
        browser=BrowserConfig(**browser_raw),
        llm=llm,
        zotero=zotero,
        project_root=config_dir,
        config_path=path,
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()
