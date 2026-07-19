from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from src.config import AppConfig
from src.models import Candidate, FetchResult
from src.utils import normalize_url, safe_filename, safe_stem, unique_path


class ArticleFetcher:
    def __init__(self, config: AppConfig):
        self.config = config
        self.context = None
        self.playwright = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        user_data_dir = self.config.browser.user_data_dir
        if not user_data_dir:
            user_data_dir = str(self.config.project_root / ".browser_profile")

        launch_args = {
            "user_data_dir": user_data_dir,
            "headless": self.config.browser.headless,
            "accept_downloads": True,
        }
        try:
            self.context = self.playwright.chromium.launch_persistent_context(channel="chrome", **launch_args)
        except Exception:
            self.context = self.playwright.chromium.launch_persistent_context(**launch_args)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def fetch(self, candidate: Candidate, staging_dir: Path) -> FetchResult:
        if not self.context:
            raise RuntimeError("ArticleFetcher must be used as a context manager")

        inspected = self.inspect(candidate)
        if inspected.error:
            return inspected
        metadata = inspected.metadata
        html = metadata.pop("_html", "")
        pdf_url = self._find_pdf_url(html, candidate.url)
        attachment_url = self._find_attachment_url(html, candidate.url)

        pdf_path = None
        attachment_path = None
        file_stem = self._article_file_stem(metadata, candidate)
        metadata["file_stem"] = file_stem
        if pdf_url:
            pdf_path = self._download_url(pdf_url, unique_path(staging_dir / f"{file_stem}.pdf"))
        if attachment_url:
            try:
                attachment_path = self._download_url(
                    attachment_url,
                    self._attachment_target(attachment_url, staging_dir, file_stem),
                )
            except Exception as exc:
                metadata["attachment_error"] = str(exc)
        metadata["pdf_url"] = pdf_url
        metadata["attachment_url"] = attachment_url
        metadata["attachment_status"] = "downloaded" if attachment_path else "none"
        return FetchResult(pdf_path, attachment_path, metadata)

    def inspect(self, candidate: Candidate) -> FetchResult:
        if not self.context:
            raise RuntimeError("ArticleFetcher must be used as a context manager")

        page = self.context.new_page()
        try:
            response = page.goto(candidate.url, wait_until="domcontentloaded", timeout=60000)
            if response and response.status >= 400:
                return FetchResult(None, None, {"status": response.status}, f"http_{response.status}")
            page.wait_for_timeout(1500)
            html = page.content()
            metadata = self._metadata_from_html(html, candidate)
            if not self._journal_allowed(metadata):
                metadata["journal_filter_required_term"] = self.config.nature.journal_name_required_term
                return FetchResult(None, None, metadata, "journal_filtered")
            metadata["_html"] = html
            return FetchResult(None, None, metadata)
        finally:
            page.close()

    def _journal_allowed(self, metadata: dict) -> bool:
        required = (self.config.nature.journal_name_required_term or "").strip().lower()
        if not required:
            return True
        return required in (metadata.get("journal") or "").lower()

    def _download_url(self, url: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.context.request.get(url, timeout=120000)
        if not response.ok:
            raise RuntimeError(f"download failed {response.status}: {url}")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type == "text/html":
            raise RuntimeError(f"download returned HTML instead of a file: {url}")
        target = self._target_from_response(target, response.headers)
        target.write_bytes(response.body())
        return target

    @staticmethod
    def _metadata_from_html(html: str, candidate: Candidate) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        metadata = {
            "title": candidate.title,
            "published": candidate.published,
            "doi": candidate.doi,
            "journal": "",
            "authors": [],
            "first_author": "",
            "year": "",
        }
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            content = meta.get("content") or ""
            if not content:
                continue
            if name == "citation_title":
                metadata["title"] = content
            elif name in {"dc.title", "og:title"} and not metadata.get("title"):
                metadata["title"] = content
            elif name in {"citation_doi", "dc.identifier"} and not metadata.get("doi"):
                metadata["doi"] = content.replace("doi:", "").strip()
            elif name in {"citation_publication_date", "dc.date", "article:published_time"}:
                metadata["published"] = content
            elif name in {"description", "dc.description", "og:description"}:
                metadata["abstract"] = content
            elif name == "citation_journal_title":
                metadata["journal"] = content
            elif name == "citation_author":
                metadata["authors"].append(content)
        if metadata["authors"]:
            metadata["first_author"] = _author_surname(metadata["authors"][0])
        metadata["year"] = _year_from_date(metadata.get("published", ""))
        metadata["title"] = _clean_title(metadata.get("title", ""), metadata.get("journal", ""))
        return metadata

    @staticmethod
    def _find_pdf_url(html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[str] = []
        fallback_candidates: list[str] = []

        def add_candidate(href: str, fallback: bool = False) -> None:
            url = normalize_url(href, page_url)
            if ".pdf" not in url.lower() and "/pdf/" not in url.lower():
                return
            target = fallback_candidates if fallback else candidates
            if url not in candidates and url not in fallback_candidates:
                target.append(url)

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            text = anchor.get_text(" ", strip=True).lower()
            class_names = " ".join(anchor.get("class") or []).lower()
            is_download_button = (
                anchor.get("data-test") == "download-pdf"
                or anchor.get("data-article-pdf") == "true"
                or "c-pdf-download__link" in class_names
                or "download pdf" in text
            )
            if is_download_button:
                add_candidate(href)

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            if href.lower().endswith(".pdf") or ".pdf?" in href.lower():
                add_candidate(href)

        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            if name == "citation_pdf_url" and meta.get("content"):
                add_candidate(meta["content"], fallback=True)
        for url in [*candidates, *fallback_candidates]:
            return url
        return ""

    @staticmethod
    def _find_attachment_url(html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        patterns = ("supplementary", "additional", "source data", "extended data")
        candidates: list[str] = []

        def is_download_like(url: str) -> bool:
            parsed = urlparse(url)
            path = parsed.path.lower()
            if normalize_url(url, page_url).rstrip("/") == normalize_url(page_url).rstrip("/"):
                return False
            if "/figures/" in path or "/tables/" in path:
                return False
            if re.search(r"\.(pdf|zip|xlsx?|docx?|csv|txt|tar|gz|7z)(?:$|[?#])", path):
                return True
            return "static-content.springer.com" in parsed.netloc.lower() or "mediaobjects" in path or "/esm/" in path

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            text = anchor.get_text(" ", strip=True).lower()
            joined = f"{href} {text}".lower()
            if any(pattern in joined for pattern in patterns):
                url = normalize_url(href, page_url)
                if is_download_like(url):
                    candidates.append(url)
        return candidates[0] if candidates else ""

    @staticmethod
    def _article_file_stem(metadata: dict, candidate: Candidate) -> str:
        journal = metadata.get("journal") or "Nature"
        first_author = metadata.get("first_author") or "Unknown"
        year = metadata.get("year") or (metadata.get("published") or candidate.published or "undated")[:4]
        title = metadata.get("title") or candidate.title or "Untitled"
        return safe_stem(f"{journal}-{first_author}-{year}-{title}", "article")

    @staticmethod
    def _attachment_target(url: str, staging_dir: Path, file_stem: str) -> Path:
        parsed = urlparse(url)
        name = safe_filename(unquote(Path(parsed.path).name), "attachment_01")
        suffix = Path(name).suffix
        if not re.search(r"\.[A-Za-z0-9]{2,6}$", suffix):
            suffix = ".dat"
        return unique_path(staging_dir / f"Supp-{file_stem}{suffix}")

    @staticmethod
    def _target_from_response(target: Path, headers: dict) -> Path:
        if target.suffix.lower() != ".dat":
            return target
        disposition = headers.get("content-disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition, re.IGNORECASE)
        if match:
            suffix = Path(unquote(match.group(1))).suffix
            if suffix:
                return unique_path(target.with_suffix(suffix))
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        suffix = {
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "application/x-zip-compressed": ".zip",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "text/plain": ".txt",
            "text/csv": ".csv",
        }.get(content_type)
        return unique_path(target.with_suffix(suffix)) if suffix else target


def _author_surname(author: str) -> str:
    author = author.strip()
    if not author:
        return "Unknown"
    if "," in author:
        return author.split(",", 1)[0].strip() or "Unknown"
    return author.split()[-1].strip() or "Unknown"


def _year_from_date(value: str) -> str:
    match = re.search(r"(19|20)\d{2}", value or "")
    return match.group(0) if match else ""


def _clean_title(title: str, journal: str) -> str:
    title = title.strip()
    journal = journal.strip()
    if journal and title.lower().endswith(f" - {journal}".lower()):
        return title[: -(len(journal) + 3)].strip()
    return title
