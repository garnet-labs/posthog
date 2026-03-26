import os
import json
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "crawl_cache"
URLS_FILE = CACHE_DIR / "_selected_urls.json"

DISCOVER_PROMPT = """\
Your goal is to find all product/feature pages for the website at {url}.

Steps:
1. Fetch {url}/robots.txt — look for Sitemap: entries
2. Fetch each sitemap XML. If it's a sitemap index, fetch the child sitemaps too.
3. From ALL URLs in the sitemaps, select only pages that describe product features,
   capabilities, integrations, platform overview, or use cases.
4. EXCLUDE: blog posts, changelog, careers, team/about, docs/tutorials, guides,
   pricing, legal, community, newsletter, handbook, case studies, customer stories,
   content marketing, thought leadership, API reference, and support/help pages.
5. Aim for 20-100 URLs. Include both top-level product pages and their sub-pages
   that describe specific features or capabilities.

IMPORTANT:
- Do NOT visit or fetch the actual pages. Only analyze URLs from sitemaps.
- If robots.txt has no sitemap, try {url}/sitemap.xml directly.

Respond with a JSON object inside a ```json``` code block matching this schema:

{output_schema}
"""


class DiscoveredUrls(BaseModel):
    urls: list[str] = Field(description="List of discovered product/feature page URLs for the target website")


async def _discover_product_urls(
    url: str,
    *,
    verbose: bool = False,
    output_fn=None,
) -> list[str]:
    from asgiref.sync import sync_to_async

    from products.tasks.backend.services.custom_prompt_executor import run_sandbox_agent_get_structured_output
    from products.tasks.backend.services.custom_prompt_runner import resolve_sandbox_context_for_local_dev

    CACHE_DIR.mkdir(exist_ok=True)

    if URLS_FILE.exists():
        cached = DiscoveredUrls.model_validate_json(URLS_FILE.read_text())
        if output_fn:
            output_fn(f"Using {len(cached.urls)} cached URLs from {URLS_FILE}")
        return cached.urls

    context = await sync_to_async(resolve_sandbox_context_for_local_dev)("PostHog/.github")
    output_schema = json.dumps(DiscoveredUrls.model_json_schema(), indent=2)
    prompt = DISCOVER_PROMPT.format(url=url, output_schema=output_schema)

    if output_fn:
        output_fn(f"Asking agent to discover product pages for {url}...")

    result = await run_sandbox_agent_get_structured_output(
        prompt=prompt,
        context=context,
        model_to_validate=DiscoveredUrls,
        step_name="discover_product_urls",
        verbose=verbose,
        output_fn=output_fn,
    )

    URLS_FILE.write_text(result.model_dump_json(indent=2))
    if output_fn:
        output_fn(f"Discovered {len(result.urls)} product URLs")
    return result.urls


def _url_to_filename(url: str) -> str:
    slug = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
    return f"{slug[:300]}.json"


def _get_page_url(metadata: dict) -> str:
    """Extract the page URL from metadata, trying all known key variants."""
    return metadata.get("url", metadata.get("sourceURL", metadata.get("source_url", "")))


def _scrape_pages(urls: list[str], *, output_fn=None) -> list[dict]:
    from firecrawl import FirecrawlApp

    # Load already-cached pages, determine which URLs still need scraping
    cached_pages: dict[str, dict] = {}
    for filepath in CACHE_DIR.glob("*.json"):
        if filepath.name.startswith("_"):
            continue
        page = json.loads(filepath.read_text())
        source_url = _get_page_url(page.get("metadata", {}))
        if source_url:
            cached_pages[source_url] = page

    uncached_urls = [u for u in urls if u not in cached_pages]

    if output_fn:
        output_fn(f"{len(cached_pages)} cached, {len(uncached_urls)} to scrape")

    if uncached_urls:
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        assert firecrawl_api_key, "FIRECRAWL_API_KEY must be set in environment variables"
        app = FirecrawlApp(api_key=firecrawl_api_key)

        if output_fn:
            output_fn(f"Batch scraping {len(uncached_urls)} URLs...")

        scrape_result = app.batch_scrape(
            uncached_urls,
            formats=["markdown", "summary", {"type": "screenshot", "fullPage": True}],
        )

        if output_fn:
            output_fn(
                f"Scrape status: {scrape_result.status}, completed: {scrape_result.completed}/{scrape_result.total}"
            )

        for doc in scrape_result.data:
            page = {
                "markdown": doc.markdown,
                "summary": doc.summary if hasattr(doc, "summary") else None,
                "screenshot": doc.screenshot if hasattr(doc, "screenshot") else None,
                "metadata": doc.metadata
                if isinstance(doc.metadata, dict)
                else vars(doc.metadata)
                if doc.metadata
                else {},
            }
            source_url = _get_page_url(page["metadata"])
            filename = _url_to_filename(source_url) if source_url else _url_to_filename(f"unknown_{len(cached_pages)}")

            filepath = CACHE_DIR / filename
            filepath.write_text(json.dumps(page, indent=2, default=str))
            cached_pages[source_url] = page
            if output_fn:
                output_fn(f"  Saved {filepath.name}")

    # Return pages in the order of the input URLs
    pages = [cached_pages[u] for u in urls if u in cached_pages]
    if output_fn:
        output_fn(f"{len(pages)} pages available")
    return pages


def crawl_website(url: str, *, verbose: bool = False, output_fn=None) -> list[dict]:
    if not url.startswith("http"):
        url = f"https://{url}"

    urls = asyncio.run(_discover_product_urls(url, verbose=verbose, output_fn=output_fn))
    if not urls:
        if output_fn:
            output_fn("No product URLs discovered")
        return []

    return _scrape_pages(urls, output_fn=output_fn)
