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


# ---------------------------------------------------------------------------
# Enrichment: add code paths to the taxonomy via multi-turn agent
# ---------------------------------------------------------------------------

ENRICHED_TAXONOMY_FILE = CACHE_DIR / "_enriched_taxonomy.json"


class EnrichedFeature(BaseModel):
    name: str = Field(description="Feature name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the feature")
    source_urls: list[str] = Field(description="Website page URLs that describe this feature")
    code_paths: list[str] = Field(
        description=(
            "Directory or file glob patterns in the codebase that implement this feature. "
            "Prefer directories over individual files (e.g. 'products/experiments/backend/*' "
            "rather than listing every file). Use glob patterns like 'some/path/*' to cover "
            "a directory and its contents."
        ),
    )


class EnrichedProduct(BaseModel):
    name: str = Field(description="Product name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the product")
    source_urls: list[str] = Field(description="Website page URLs that describe this product")
    code_paths: list[str] = Field(
        description=(
            "Top-level directory or file glob patterns for this product. "
            "These are the root code paths — feature-level paths provide more specificity."
        ),
    )
    features: list[EnrichedFeature] = Field(description="Features within this product, each with code paths")


class EnrichedProductTurnOutput(BaseModel):
    products: list[EnrichedProduct] = Field(
        description=(
            "One or more enriched products. Usually one (the input product enriched with code paths). "
            "Return multiple if a nested feature should be promoted to a separate product based on "
            "how the code is organized."
        ),
    )


class EnrichedTaxonomy(BaseModel):
    products: list[EnrichedProduct] = Field(description="All products with code paths")


_ENRICHMENT_PREAMBLE = """\
You are enriching a product feature taxonomy with code paths from the PostHog codebase.

The codebase is available on disk. Use file search, grep, and code reading to find where each
product and feature is implemented.

## Rules

1. For each product and feature, find the code directories/files that implement it.
2. Prefer **directory-level glob patterns** over individual files:
   - Good: `products/experiments/backend/*`, `frontend/src/scenes/experiments/*`
   - Bad: `products/experiments/backend/models.py`, `products/experiments/backend/api.py`, ...
3. Include both backend and frontend paths when they exist.
4. Look at `products/` directory first — most products have a dedicated directory there.
   Also check `posthog/` for older code, `frontend/src/scenes/` for frontend scenes,
   and `frontend/src/queries/` for query-related code.
5. If a feature listed under a product is actually implemented as a **separate product**
   in the codebase (has its own `products/` directory), promote it: return it as a separate
   product entry in the output list.
6. If a feature has no distinct code path (it's part of the parent product's code), set its
   code_paths to an empty list.
7. Do NOT guess paths — verify they exist by listing or searching the filesystem."""

_ENRICHMENT_INITIAL_PROMPT = """\
{preamble}

You will enrich **{total_products} product(s)** one at a time. I will send each product in a
separate message. For each one, find code paths and respond with the enriched output.

---

## Product 1 of {total_products}

<product>
{product_json}
</product>

---

Investigate the codebase to find where this product and its features are implemented.
Respond with a JSON object inside a ```json``` code block matching this schema:

{output_schema}
"""

_ENRICHMENT_FOLLOWUP_PROMPT = """\
## Product {index} of {total_products}

<product>
{product_json}
</product>

---

Investigate the codebase to find where this product and its features are implemented.
Respond with a JSON object inside a ```json``` code block matching this schema:

{output_schema}
"""


async def enrich_taxonomy(
    taxonomy: FeatureTaxonomy,
    *,
    verbose: bool = False,
    output_fn=None,
) -> EnrichedTaxonomy:
    from asgiref.sync import sync_to_async

    from products.tasks.backend.services.custom_prompt_multi_turn_runner import (
        end_session,
        send_followup,
        start_session,
    )
    from products.tasks.backend.services.custom_prompt_runner import resolve_sandbox_context_for_local_dev

    if ENRICHED_TAXONOMY_FILE.exists():
        cached = EnrichedTaxonomy.model_validate_json(ENRICHED_TAXONOMY_FILE.read_text())
        if output_fn:
            total_features = sum(len(p.features) for p in cached.products)
            output_fn(f"Using cached enriched taxonomy: {len(cached.products)} products, {total_features} features")
        return cached

    total = len(taxonomy.products)
    if total == 0:
        raise ValueError("No products in taxonomy to enrich")

    if output_fn:
        output_fn(f"Starting multi-turn enrichment: {total} product(s)")

    context = await sync_to_async(resolve_sandbox_context_for_local_dev)("PostHog/posthog")
    output_schema = json.dumps(EnrichedProductTurnOutput.model_json_schema(), indent=2)

    # Turn 1: first product
    first_product = taxonomy.products[0]
    initial_prompt = _ENRICHMENT_INITIAL_PROMPT.format(
        preamble=_ENRICHMENT_PREAMBLE,
        total_products=total,
        product_json=first_product.model_dump_json(indent=2),
        output_schema=output_schema,
    )

    session, first_result = await start_session(
        prompt=initial_prompt,
        context=context,
        model=EnrichedProductTurnOutput,
        step_name="enrich_taxonomy",
        verbose=verbose,
        output_fn=output_fn,
    )

    all_enriched: list[EnrichedProduct] = list(first_result.products)
    if output_fn:
        output_fn(f"Product 1/{total} done: {first_product.name} -> {len(first_result.products)} product(s)")

    # Turns 2..N
    for i, product in enumerate(taxonomy.products[1:], start=2):
        if output_fn:
            output_fn(f"Enriching product {i}/{total}: {product.name}...")

        followup_prompt = _ENRICHMENT_FOLLOWUP_PROMPT.format(
            index=i,
            total_products=total,
            product_json=product.model_dump_json(indent=2),
            output_schema=output_schema,
        )

        result = await send_followup(
            session,
            followup_prompt,
            EnrichedProductTurnOutput,
            label=f"product_{i}_of_{total}",
        )

        all_enriched.extend(result.products)
        if output_fn:
            output_fn(f"Product {i}/{total} done: {product.name} -> {len(result.products)} product(s)")

    await end_session(session)

    enriched_taxonomy = EnrichedTaxonomy(products=all_enriched)
    ENRICHED_TAXONOMY_FILE.write_text(enriched_taxonomy.model_dump_json(indent=2))

    if output_fn:
        total_features = sum(len(p.features) for p in enriched_taxonomy.products)
        output_fn(f"Enrichment complete: {len(enriched_taxonomy.products)} products, {total_features} features")

    return enriched_taxonomy


def run_enrich_taxonomy(*, verbose: bool = False, output_fn=None) -> EnrichedTaxonomy:
    taxonomy_result = run_build_taxonomy(verbose=verbose, output_fn=output_fn)
    return asyncio.run(enrich_taxonomy(taxonomy_result, verbose=verbose, output_fn=output_fn))
