import json
import asyncio
import logging

from pydantic import BaseModel, Field

from products.hawgs.backend.crawl.crawl import CACHE_DIR, _get_page_url

logger = logging.getLogger(__name__)

TAXONOMY_FILE = CACHE_DIR / "_taxonomy.json"

TAXONOMY_PROMPT = """\
You are analyzing scraped product pages from a website to build a hierarchical feature taxonomy.

Below is a JSON array of pages. Each entry has: url, title, description, screenshot_url, and markdown content.

<pages>
{pages_json}
</pages>

Your task:
1. Analyze all pages to identify distinct products and their features.
2. A "product" is a top-level offering (e.g. "Product analytics", "Session replay").
3. A "feature" is a specific capability within a product (e.g. "Funnels" within "Product analytics").
4. Some pages describe a product, others describe features within a product. Cross-reference
   the content to build the hierarchy.
5. If a capability doesn't clearly belong under a product, place it under a "Platform" product.
6. Use the codebase to ground your findings — check if the products/features you identify
   correspond to actual code in the repository (look at the `products/` directory structure).
   This helps validate that what the website describes actually exists as a distinct product/feature.

Rules:
- Every feature must belong to exactly one product.
- Use the website's own naming and descriptions, don't invent new names.
- Include source_urls: which page(s) informed each product/feature.
- Keep descriptions concise (1-2 sentences).
- Do NOT include pricing, company info, or non-product pages.

Respond with a JSON object inside a ```json``` code block matching this schema:

{output_schema}
"""


class Feature(BaseModel):
    name: str = Field(description="Feature name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the feature")
    source_urls: list[str] = Field(description="Website page URLs that describe this feature")


class Product(BaseModel):
    name: str = Field(description="Product name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the product")
    source_urls: list[str] = Field(description="Website page URLs that describe this product")
    features: list[Feature] = Field(description="Features within this product")


class FeatureTaxonomy(BaseModel):
    products: list[Product] = Field(description="Top-level products, each containing their features")


def _load_pages_context() -> list[dict]:
    """Load all cached pages and extract the fields needed for the taxonomy prompt."""
    pages = []
    for filepath in sorted(CACHE_DIR.glob("*.json")):
        if filepath.name.startswith("_"):
            continue
        raw = json.loads(filepath.read_text())
        metadata = raw.get("metadata", {})
        pages.append(
            {
                "url": _get_page_url(metadata),
                "title": metadata.get("title", ""),
                "description": metadata.get("description", metadata.get("og_description", "")),
                "screenshot_url": raw.get("screenshot", ""),
                "markdown": raw.get("markdown", ""),
            }
        )
    return pages


async def build_taxonomy(
    *,
    verbose: bool = False,
    output_fn=None,
) -> FeatureTaxonomy:
    from asgiref.sync import sync_to_async

    from products.tasks.backend.services.custom_prompt_executor import run_sandbox_agent_get_structured_output
    from products.tasks.backend.services.custom_prompt_runner import resolve_sandbox_context_for_local_dev

    if TAXONOMY_FILE.exists():
        cached = FeatureTaxonomy.model_validate_json(TAXONOMY_FILE.read_text())
        if output_fn:
            total_features = sum(len(p.features) for p in cached.products)
            output_fn(f"Using cached taxonomy: {len(cached.products)} products, {total_features} features")
        return cached

    pages = _load_pages_context()
    if not pages:
        raise RuntimeError(f"No cached pages found in {CACHE_DIR}. Run crawl_website first.")

    if output_fn:
        output_fn(f"Building taxonomy from {len(pages)} pages...")

    context = await sync_to_async(resolve_sandbox_context_for_local_dev)("PostHog/posthog")
    output_schema = json.dumps(FeatureTaxonomy.model_json_schema(), indent=2)
    pages_json = json.dumps(pages, indent=2)
    prompt = TAXONOMY_PROMPT.format(pages_json=pages_json, output_schema=output_schema)

    if output_fn:
        output_fn(f"Prompt size: ~{len(prompt)} chars ({len(prompt) // 4}~ tokens)")

    result = await run_sandbox_agent_get_structured_output(
        prompt=prompt,
        context=context,
        model_to_validate=FeatureTaxonomy,
        step_name="build_taxonomy",
        verbose=verbose,
        output_fn=output_fn,
    )

    TAXONOMY_FILE.write_text(result.model_dump_json(indent=2))
    if output_fn:
        total_features = sum(len(p.features) for p in result.products)
        output_fn(f"Taxonomy built: {len(result.products)} products, {total_features} features")
    return result


def run_build_taxonomy(*, verbose: bool = False, output_fn=None) -> FeatureTaxonomy:
    return asyncio.run(build_taxonomy(verbose=verbose, output_fn=output_fn))
