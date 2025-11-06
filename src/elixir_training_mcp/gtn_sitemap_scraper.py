"""GTN sitemap scraper: extract JSON-LD from GTN pages listed in sitemap.

This module provides functionality to scrape Galaxy Training Network (GTN) tutorial
and slides pages, extracting their embedded JSON-LD metadata for knowledge graph construction.

Features:
- Sitemap discovery and parsing (handles nested sitemap indexes)
- Robots.txt respect with configurable user agent
- Rate limiting and politeness delays
- Concurrent fetching with semaphore control
- JSON-LD extraction via extruct
- Automatic filtering to LearningResource objects

Flow:
- Fetch sitemap (and nested sitemaps if any)
- Collect page URLs (filter tutorials/slides)
- Respect robots.txt (disallow) and rate-limit
- Fetch HTML and extract JSON-LD via extruct
- Save one .jsonld file per page for later KG building
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import extruct
import httpx


DEFAULT_BASE_URL = "https://training.galaxyproject.org"


@dataclass
class ScrapeConfig:
    base_url: str = DEFAULT_BASE_URL
    sitemap_paths: tuple[str, ...] = ("/sitemap.xml", "/training-material/sitemap.xml")
    out_dir: Path = Path("data/gtn_jsonld")
    user_agent: str = "ELIXIR-TrP-KG-bot/1.0 (https://github.com/elixir-europe-training/ELIXIR-TrP-KG-training-metadata)"
    timeout_s: int = 30
    max_concurrency: int = 5
    request_delay_s: float = 0.5
    respect_robots: bool = True
    filter_learning_resource_only: bool = True


class GTNSitemapScraper:
    def __init__(self, config: ScrapeConfig) -> None:
        self.cfg = config
        self.cfg.out_dir.mkdir(parents=True, exist_ok=True)
        self._sem = asyncio.Semaphore(self.cfg.max_concurrency)
        self._robots: RobotFileParser | None = None

    async def _ensure_robots(self) -> None:
        """Fetch and parse robots.txt if respect_robots is enabled.

        Attempts to download and parse the site's robots.txt file. Falls back to
        allowing all access if robots.txt cannot be fetched.
        """
        if not self.cfg.respect_robots or self._robots is not None:
            return
        robots_url = f"{self.cfg.base_url.rstrip('/')}/robots.txt"
        rp = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
                resp = await client.get(robots_url)
                resp.raise_for_status()
                rp.parse(resp.text.splitlines())
        except (httpx.HTTPError, httpx.TimeoutException):
            # If robots cannot be fetched, default to allowing
            rp.parse(["User-agent: *", "Allow: /"])
        self._robots = rp

    def _allowed(self, url: str) -> bool:
        """Check if URL is allowed per robots.txt rules.

        Args:
            url: URL to check for crawl permission

        Returns:
            True if URL is allowed or robots checking is disabled, False otherwise
        """
        if not self.cfg.respect_robots or self._robots is None:
            return True
        return self._robots.can_fetch(self.cfg.user_agent, url)

    async def fetch_sitemap_urls(self) -> list[str]:
        """Fetch URLs from sitemap or sitemap index (depth 1)."""
        urls: list[str] = []
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            # Try each sitemap path
            for rel in self.cfg.sitemap_paths:
                sitemap_url = f"{self.cfg.base_url.rstrip('/')}{rel}"
                try:
                    r = await client.get(sitemap_url)
                    if r.status_code != 200:
                        continue
                    # Very simple XML parsing without extra deps
                    text = r.text
                    if "<sitemapindex" in text:
                        # collect nested sitemap <loc>
                        nested = _extract_xml_tags(text, "loc")
                        for sm in nested:
                            try:
                                rs = await client.get(sm)
                                rs.raise_for_status()
                                urls.extend(_extract_xml_tags(rs.text, "loc"))
                            except (httpx.HTTPError, httpx.TimeoutException):
                                continue
                    else:
                        urls.extend(_extract_xml_tags(text, "loc"))
                except (httpx.HTTPError, httpx.TimeoutException):
                    continue

        # Filter to GTN training pages likely to contain JSON-LD
        # Target tutorial.html and slides.html pages (not FAQs, workflows, experiences)
        urls = [
            u
            for u in urls
            if "/training-material/topics/" in u
            and "/tutorials/" in u
            and (
                u.endswith("/tutorial.html")
                or u.endswith("/slides.html")
                or "/slides-plain.html" in u
            )
            and "/faqs/" not in u
            and "/workflows/" not in u
            and "/experiences/" not in u
        ]

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    async def scrape_all(self, max_urls: int | None = None) -> list[Path]:
        await self._ensure_robots()
        all_urls = await self.fetch_sitemap_urls()
        if max_urls is not None:
            all_urls = all_urls[:max_urls]

        out_files: list[Path] = []
        async with httpx.AsyncClient(
            timeout=self.cfg.timeout_s,
            headers={"User-Agent": self.cfg.user_agent},
            follow_redirects=True,
        ) as client:
            tasks = [self._scrape_one(client, url) for url in all_urls]
            for coro_chunk in _chunked(tasks, self.cfg.max_concurrency):
                results = await asyncio.gather(*coro_chunk, return_exceptions=True)
                # brief politeness delay between chunks
                await asyncio.sleep(self.cfg.request_delay_s)
                for res in results:
                    if isinstance(res, Path):
                        out_files.append(res)
        return out_files

    async def _scrape_one(self, client: httpx.AsyncClient, url: str) -> Path | None:
        if not self._allowed(url):
            return None

        async with self._sem:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
                data = extruct.extract(
                    html,
                    base_url=url,
                    syntaxes=["json-ld"],
                    uniform=True,
                ).get("json-ld", [])

                # Filter to LearningResource objects if requested
                if self.cfg.filter_learning_resource_only:
                    data = [obj for obj in data if _is_learning_resource(obj)]

                if not data:
                    return None

                out_file = self._output_path_for(url)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                with out_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return out_file
            except (httpx.HTTPError, httpx.TimeoutException, OSError, ValueError):
                return None

    def _output_path_for(self, url: str) -> Path:
        """Generate safe filesystem path for a URL's JSON-LD output.

        Converts URL path to a safe filename by replacing slashes with underscores.

        Args:
            url: Source URL being scraped

        Returns:
            Path object for the output .jsonld file
        """
        parsed = urlparse(url)
        safe = parsed.path.strip("/").replace("/", "_")
        if not safe:
            safe = "index"
        if not safe.endswith(".jsonld"):
            safe = f"{safe}.jsonld"
        return self.cfg.out_dir / safe


def _extract_xml_tags(xml: str, tag: str) -> list[str]:
    """Extract text content from all instances of an XML tag.

    Minimalistic tag extraction without XML parser dependencies.
    Sufficient for extracting <loc> tags from sitemaps.

    Args:
        xml: XML document as string
        tag: Tag name to extract (e.g., "loc")

    Returns:
        List of text content from all matching tags
    """
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    out: list[str] = []
    i = 0
    while True:
        i = xml.find(open_tag, i)
        if i == -1:
            break
        j = xml.find(close_tag, i + len(open_tag))
        if j == -1:
            break
        out.append(xml[i + len(open_tag) : j].strip())
        i = j + len(close_tag)
    return out


def _is_learning_resource(obj: Any) -> bool:
    """Check if a JSON-LD object is a LearningResource.

    Inspects the @type field (string or list) and checks for "LearningResource"
    (case-insensitive).

    Args:
        obj: JSON-LD object (dictionary)

    Returns:
        True if object has @type of LearningResource, False otherwise
    """
    if not isinstance(obj, dict):
        return False
    ty = obj.get("@type")
    if isinstance(ty, str):
        return ty.lower() == "learningresource"
    if isinstance(ty, list):
        return any(isinstance(t, str) and t.lower() == "learningresource" for t in ty)
    return False


def _chunked(iterable: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Split an iterable into fixed-size chunks.

    Args:
        iterable: Input iterable to chunk
        size: Maximum number of items per chunk

    Yields:
        Lists of items, each containing up to 'size' elements
    """
    buf: list[Any] = []
    for item in iterable:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


def cli() -> None:
    parser = argparse.ArgumentParser(description="Scrape GTN sitemap and extract JSON-LD")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="GTN base URL")
    parser.add_argument("--out-dir", default="data/gtn_jsonld", help="Output directory for .jsonld files")
    parser.add_argument("--max-urls", type=int, default=50, help="Limit number of URLs (for testing)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent fetches")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between request chunks (seconds)")
    parser.add_argument("--no-robots", action="store_true", help="Ignore robots.txt (not recommended)")
    parser.add_argument(
        "--include-non-learning",
        action="store_true",
        help="Do not filter to LearningResource objects only",
    )
    args = parser.parse_args()

    cfg = ScrapeConfig(
        base_url=args.base_url,
        out_dir=Path(args.out_dir),
        max_concurrency=args.concurrency,
        request_delay_s=args.delay,
        respect_robots=not args.no_robots,
        filter_learning_resource_only=not args.include_non_learning,
    )

    async def _run() -> None:
        scraper = GTNSitemapScraper(cfg)
        files = await scraper.scrape_all(max_urls=args.max_urls)
        print(f"Saved {len(files)} JSON-LD files to {cfg.out_dir}")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()


