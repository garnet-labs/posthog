import json
import os
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

load_dotenv()
from firecrawl.v2.types import ScrapeOptions

CACHE_DIR = Path(__file__).parent / "crawl_cache"


def crawl_website(url: str) -> list[dict]:
    if not url.startswith("http"):
        url = f"https://{url}"

    CACHE_DIR.mkdir(exist_ok=True)

    cached = list(CACHE_DIR.glob("*.json"))
    if cached:
        print(f"Using {len(cached)} cached pages from {CACHE_DIR}")
        return [json.loads(f.read_text()) for f in sorted(cached)]

    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    assert firecrawl_api_key, "FIRECRAWL_API_KEY must be set in environment variables"
    app = FirecrawlApp(api_key=firecrawl_api_key)

    scrape_opts = ScrapeOptions(
        only_main_content=False,
        max_age=172800000,
        formats=["markdown", {"type": "screenshot", "fullPage": True}],
    )
    print(f"Starting crawl of {url} (limit=35, max_depth=2)...")
    crawl_result = app.crawl(
        url,
        sitemap="include",
        crawl_entire_domain=False,
        limit=35,
        exclude_paths=[
            r"blog.*",
            r"changelog.*",
            r"careers.*",
            r"team.*",
            r"about.*",
            r"docs.*",
            r"tutorials.*",
            r"pricing.*",
            r"legal.*",
            r"terms.*",
            r"privacy.*",
            r"community.*",
            r"newsletter.*",
            r"handbook.*",
        ],
        prompt="Prioritize pages that describe product capabilities, features, integrations, and use cases. Follow links to individual product/feature pages, solution pages, and 'how it works' sections. Don't crawl documentation, handbooks, blog posts, news, careers, team, about, legal pages.",
        max_discovery_depth=2,
        scrape_options=scrape_opts,
    )

    print(f"Crawl result status: {crawl_result.status}")
    print(f"Total pages discovered: {crawl_result.total}")
    print(f"Pages completed: {crawl_result.completed}")
    print(f"Credits used: {crawl_result.credits_used}")
    print(f"Data length: {len(crawl_result.data) if crawl_result.data else 0}")

    if not crawl_result.data:
        print("No data returned. Full result:")
        print(vars(crawl_result))
        return []

    pages = []
    for i, doc in enumerate(crawl_result.data):
        page = {
            "markdown": doc.markdown,
            "screenshot": doc.screenshot if hasattr(doc, "screenshot") else None,
            "metadata": doc.metadata if isinstance(doc.metadata, dict) else vars(doc.metadata) if doc.metadata else {},
        }
        source_url = page["metadata"].get("sourceURL", page["metadata"].get("source_url", f"page_{i}"))
        slug = source_url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
        filename = f"{i:03d}_{slug[:80]}.json"

        filepath = CACHE_DIR / filename
        filepath.write_text(json.dumps(page, indent=2, default=str))
        pages.append(page)
        print(f"Saved {filepath.name}")

    print(f"Crawled and cached {len(pages)} pages")
    return pages
