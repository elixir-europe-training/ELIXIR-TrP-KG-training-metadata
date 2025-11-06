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
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import extruct
import httpx
from pyld import jsonld
from rdflib import Graph

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


JSONLD_DIR = Path("data/gtn_jsonld")
OUTPUT_TTL = Path("data/gtn_output.ttl")

# ---- Local contexts ----
LOCAL_CONTEXT = {
    "@vocab": "https://schema.org/",
    "schema": "https://schema.org/",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "bioschemas": "https://bioschemas.org/"
}

# Map known remote context URLs to local, inline JSON objects.
CONTEXT_MAP = {
    "http://schema.org": {"@context": "https://schema.org/"},
    "https://schema.org": {"@context": "https://schema.org/"},
    "http://schema.org/": {"@context": "https://schema.org/"},
    "https://schema.org/": {"@context": "https://schema.org/"},
    "http://purl.org/dc/terms/": {"@context": {"dcterms": "http://purl.org/dc/terms/"}},
    "http://purl.org/dc/terms": {"@context": {"dcterms": "http://purl.org/dc/terms/"}},
    "https://bioschemas.org": {"@context": {"bioschemas": "https://bioschemas.org/"}},
    "https://bioschemas.org/": {"@context": {"bioschemas": "https://bioschemas.org/"}}
}

# ---- Offline document loader with correct signature ----
def offline_loader(url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Custom document loader for pyld that blocks remote context fetches.

    This loader intercepts pyld's context resolution and returns local definitions
    for known vocabulary URLs, preventing any network requests during JSON-LD processing.

    Args:
        url: Context URL that pyld is trying to fetch
        options: Optional pyld loader options (unused)

    Returns:
        Document loader response dict with local context definition

    Raises:
        RuntimeError: If URL is not in the local CONTEXT_MAP (blocks unknown contexts)
    """
    # Normalize URL (strip trailing '#')
    key = url.rstrip("#")
    if key in CONTEXT_MAP:
        return {
            "contextUrl": None,
            "documentUrl": url,
            "document": CONTEXT_MAP[key]
        }
    # Block any other remote fetch
    raise RuntimeError(f"Blocked remote fetch: {url}")

# Install the loader globally
jsonld.set_document_loader(offline_loader)

def promote_id_to_atid(obj: Any) -> Any:
    """Recursively promote 'id' to '@id' and remove nested @context."""
    if isinstance(obj, dict):
        if "id" in obj and "@id" not in obj:
            obj["@id"] = obj.pop("id")
        # Remove nested @context to prevent remote lookups later
        if "@context" in obj:
            obj.pop("@context", None)
        for k, v in list(obj.items()):
            obj[k] = promote_id_to_atid(v)
        return obj
    if isinstance(obj, list):
        return [promote_id_to_atid(x) for x in obj]
    return obj


def ensure_top_level_id(doc: dict[str, Any]) -> dict[str, Any]:
    """Ensure document has an @id, fallback to url/identifier or blank node."""
    if isinstance(doc, dict) and "@id" not in doc:
        doc["@id"] = doc.get("url") or doc.get("identifier") or "_:resource"
    return doc


def load_jsonld_file(path: Path) -> list[dict[str, Any]]:
    """Load and prepare JSON-LD nodes from a file for offline processing.

    Reads a JSON-LD file, promotes plain 'id' to '@id', removes nested @context
    to prevent remote fetches, and flattens @graph structures.

    Args:
        path: Path to .jsonld file to load

    Returns:
        List of cleaned JSON-LD node dictionaries ready for expansion

    Raises:
        json.JSONDecodeError: If file contains invalid JSON
        OSError: If file cannot be read
    """
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else [data]

    nodes: list[dict[str, Any]] = []
    for item in items:
        # Flatten @graph if present
        if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
            for x in item["@graph"]:
                x = promote_id_to_atid(deepcopy(x))
                x = ensure_top_level_id(x)
                nodes.append(x)
        else:
            item = promote_id_to_atid(deepcopy(item))
            item = ensure_top_level_id(item)
            nodes.append(item)
    return nodes


def nodes_to_nquads(nodes: list[dict[str, Any]]) -> Any:
    """Convert JSON-LD nodes to N-Quads format using offline context expansion.

    Wraps nodes in a controlled @context envelope using LOCAL_CONTEXT, expands
    with pyld (using offline_loader), and converts to N-Quads serialization.

    Args:
        nodes: List of JSON-LD node dictionaries (already cleaned by load_jsonld_file)

    Returns:
        N-Quads serialization as a string

    Raises:
        RuntimeError: If pyld tries to fetch an unknown context URL
        ValueError: If JSON-LD expansion fails
    """
    doc = {"@context": LOCAL_CONTEXT, "@graph": nodes}
    expanded = jsonld.expand(doc)  # uses only our local context + offline loader
    nquads = jsonld.to_rdf(expanded, options={"format": "application/n-quads"})
    return nquads


def jsonld_to_ttl() -> None:
    """Main entry point: load all JSON-LD files and serialize to Turtle.

    Processes all .jsonld files in JSONLD_DIR, converts them to RDF triples using
    offline context expansion, and serializes the combined graph to OUTPUT_TTL.

    The function:
    1. Discovers all .jsonld files recursively
    2. Loads and cleans each file (promotes id to @id, strips nested contexts)
    3. Converts to N-Quads via pyld with offline loader
    4. Merges into single rdflib Graph
    5. Serializes to Turtle format with bound prefixes

    Raises:
        json.JSONDecodeError: If any file contains invalid JSON (logged, continues)
        OSError: If output directory cannot be created
        RuntimeError: If unknown context URLs are encountered
    """
    files = sorted(JSONLD_DIR.rglob("*.jsonld"))
    print(f"📂 Found {len(files)} JSON-LD files under {JSONLD_DIR}")

    g = Graph()
    g.bind("schema", "https://schema.org/")
    g.bind("dcterms", "http://purl.org/dc/terms/")
    g.bind("prov", "http://www.w3.org/ns/prov#")
    g.bind("bioschemas", "https://bioschemas.org/")

    ok = err = 0
    for i, fp in enumerate(files, 1):
        try:
            nodes = load_jsonld_file(fp)
            if not nodes:
                ok += 1
            else:
                nquads = nodes_to_nquads(nodes)
                g.parse(data=nquads, format="nquads")
                ok += 1
        except (json.JSONDecodeError, OSError, RuntimeError, ValueError) as e:
            err += 1
            print(f" {fp.name}: {e}")

        if i % 100 == 0 or i == len(files):
            print(f"  Processed {i}/{len(files)} | triples: {len(g):,} | files OK:{ok} ERR:{err}")

    OUTPUT_TTL.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(OUTPUT_TTL, format="turtle")
    print(f"\n Saved {len(g):,} triples to {OUTPUT_TTL}")


if __name__ == "__main__":
    cli()
    jsonld_to_ttl()
