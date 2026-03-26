import json
import asyncio
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from products.hawgs.backend.crawl.crawl import _get_page_url, cache_dir_for_domain, urls_file_for_domain

logger = logging.getLogger(__name__)


def _taxonomy_file(domain: str):
    return cache_dir_for_domain(domain) / "_taxonomy.json"


def _enriched_taxonomy_file(domain: str):
    return cache_dir_for_domain(domain) / "_enriched_taxonomy.json"


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
5. **Pricing signal:** If the pricing page lists a capability as a separately priced line item
   or a distinct plan tier, treat it as a top-level product, not a feature. Pricing structure
   is the strongest signal for what the company considers a standalone product.
6. If a capability doesn't clearly belong under a product, place it under a "Platform" product.
7. Use the codebase to ground your findings — check if the products/features you identify
   correspond to actual code in the repository. This helps validate that what the website
   describes actually exists as a distinct product/feature.

Rules:
- Every feature must belong to exactly one product.
- Use the website's own naming and descriptions, don't invent new names.
- Include source_urls: which page(s) informed each product/feature.
- Keep descriptions concise (1-2 sentences).
- Do NOT include company info or non-product pages in the taxonomy output, but DO use pricing
  page content to inform product vs. feature classification.

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


def _load_pages_context(domain: str) -> list[dict]:
    """Load all cached pages, ordered by the URL list in _selected_urls.json."""
    cache_dir = cache_dir_for_domain(domain)
    urls_file = urls_file_for_domain(domain)

    # Build a lookup from URL to page data
    pages_by_url: dict[str, dict] = {}
    for filepath in cache_dir.glob("*.json"):
        if filepath.name.startswith("_"):
            continue
        raw = json.loads(filepath.read_text())
        metadata = raw.get("metadata", {})
        url = _get_page_url(metadata)
        if url and url not in pages_by_url:
            pages_by_url[url] = {
                "url": url,
                "title": metadata.get("title", ""),
                "description": metadata.get("description", metadata.get("og_description", "")),
                "screenshot_url": raw.get("screenshot", ""),
                "markdown": raw.get("markdown", ""),
            }

    # Order by _selected_urls.json, then append any extras
    ordered: list[dict] = []
    if urls_file.exists():
        url_order = json.loads(urls_file.read_text()).get("urls", [])
        for url in url_order:
            if url in pages_by_url:
                ordered.append(pages_by_url.pop(url))

    # Append any remaining pages not in the URL list
    ordered.extend(pages_by_url.values())
    return ordered


async def build_taxonomy(
    domain: str,
    repository: str,
    *,
    verbose: bool = False,
    output_fn=None,
) -> FeatureTaxonomy:
    from asgiref.sync import sync_to_async

    from products.tasks.backend.services.custom_prompt_executor import run_sandbox_agent_get_structured_output
    from products.tasks.backend.services.custom_prompt_runner import resolve_sandbox_context_for_local_dev

    taxonomy_file = _taxonomy_file(domain)
    if taxonomy_file.exists():
        cached = FeatureTaxonomy.model_validate_json(taxonomy_file.read_text())
        if output_fn:
            total_features = sum(len(p.features) for p in cached.products)
            output_fn(f"Using cached taxonomy: {len(cached.products)} products, {total_features} features")
        return cached

    pages = _load_pages_context(domain)
    if not pages:
        raise RuntimeError(f"No cached pages found for {domain}. Run crawl_website first.")

    if output_fn:
        output_fn(f"Building taxonomy from {len(pages)} pages...")

    context = await sync_to_async(resolve_sandbox_context_for_local_dev)(repository)
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

    taxonomy_file.write_text(result.model_dump_json(indent=2))
    if output_fn:
        total_features = sum(len(p.features) for p in result.products)
        output_fn(f"Taxonomy built: {len(result.products)} products, {total_features} features")
    return result


def run_build_taxonomy(domain: str, repository: str, *, verbose: bool = False, output_fn=None) -> FeatureTaxonomy:
    return asyncio.run(build_taxonomy(domain, repository, verbose=verbose, output_fn=output_fn))


# ---------------------------------------------------------------------------
# Enrichment: add code paths to the taxonomy via multi-turn agent
# ---------------------------------------------------------------------------


class EnrichedFeature(BaseModel):
    name: str = Field(description="Feature name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the feature")
    source_urls: list[str] = Field(description="Website page URLs that describe this feature")
    code_paths: list[str] = Field(
        description=(
            "Durable directory or file glob patterns in the codebase that implement this feature. "
            "Prefer semantically meaningful directories over individual files (e.g. "
            "'products/experiments/backend/*' rather than listing every file). Use glob patterns "
            "like 'some/path/*' to cover a directory and its contents."
        ),
    )


class EnrichedProduct(BaseModel):
    name: str = Field(description="Product name as used on the website")
    description: str = Field(description="Concise 1-2 sentence description of the product")
    source_urls: list[str] = Field(description="Website page URLs that describe this product")
    code_paths: list[str] = Field(
        description=(
            "Durable top-level directory or file glob patterns for this product. "
            "These are the root code paths — feature-level paths provide more specificity."
        ),
    )
    features: list[EnrichedFeature] = Field(description="Features within this product, each with code paths")


class EnrichedProductTurnOutput(BaseModel):
    products: list[EnrichedProduct] = Field(
        description=(
            "One or more enriched products. Usually one (the input product enriched with code paths). "
            "Return multiple if a nested feature should be promoted to a separate product, or if this "
            "turn reveals other clearly related products/features that should be added based on the "
            "codebase structure."
        ),
    )


class EnrichedTaxonomy(BaseModel):
    products: list[EnrichedProduct] = Field(description="All products with code paths")


@dataclass
class EnrichedTaxonomyAccumulator:
    products: list[EnrichedProduct] = field(default_factory=list)

    def add_products(self, products: list[EnrichedProduct]) -> None:
        product_indices = {self._normalize_name(product.name): index for index, product in enumerate(self.products)}

        for product in products:
            normalized_product = self._normalize_product(product)
            key = self._normalize_name(normalized_product.name)

            if key not in product_indices:
                product_indices[key] = len(self.products)
                self.products.append(normalized_product)
                continue

            existing = self.products[product_indices[key]]
            self.products[product_indices[key]] = EnrichedProduct(
                name=existing.name or normalized_product.name,
                description=self._pick_richer_description(existing.description, normalized_product.description),
                source_urls=self._dedupe_strings([*existing.source_urls, *normalized_product.source_urls]),
                code_paths=self._dedupe_strings([*existing.code_paths, *normalized_product.code_paths]),
                features=self._merge_features([*existing.features, *normalized_product.features]),
            )

    def format_existing_products(self) -> str:
        if not self.products:
            return "- None yet"

        lines: list[str] = []
        for product in self.products:
            feature_names = [feature.name for feature in product.features[:6]]
            features_summary = ", ".join(feature_names) if feature_names else "no features yet"
            if len(product.features) > 6:
                features_summary += ", ..."

            lines.append(f"- {product.name}: {features_summary}")

        return "\n".join(lines)

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.casefold().split())

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue

            deduped.append(normalized)
            seen.add(normalized)

        return deduped

    @staticmethod
    def _pick_richer_description(*descriptions: str) -> str:
        cleaned = [description.strip() for description in descriptions if description.strip()]
        if not cleaned:
            return ""

        return max(cleaned, key=len)

    @classmethod
    def _normalize_feature(cls, feature: EnrichedFeature) -> EnrichedFeature:
        return EnrichedFeature(
            name=feature.name.strip(),
            description=feature.description.strip(),
            source_urls=cls._dedupe_strings(feature.source_urls),
            code_paths=cls._dedupe_strings(feature.code_paths),
        )

    @classmethod
    def _merge_features(cls, features: list[EnrichedFeature]) -> list[EnrichedFeature]:
        merged: list[EnrichedFeature] = []
        feature_indices: dict[str, int] = {}

        for feature in features:
            normalized_feature = cls._normalize_feature(feature)
            key = cls._normalize_name(normalized_feature.name)

            if key not in feature_indices:
                feature_indices[key] = len(merged)
                merged.append(normalized_feature)
                continue

            existing = merged[feature_indices[key]]
            merged[feature_indices[key]] = EnrichedFeature(
                name=existing.name or normalized_feature.name,
                description=cls._pick_richer_description(existing.description, normalized_feature.description),
                source_urls=cls._dedupe_strings([*existing.source_urls, *normalized_feature.source_urls]),
                code_paths=cls._dedupe_strings([*existing.code_paths, *normalized_feature.code_paths]),
            )

        return merged

    @classmethod
    def _normalize_product(cls, product: EnrichedProduct) -> EnrichedProduct:
        return EnrichedProduct(
            name=product.name.strip(),
            description=product.description.strip(),
            source_urls=cls._dedupe_strings(product.source_urls),
            code_paths=cls._dedupe_strings(product.code_paths),
            features=cls._merge_features(product.features),
        )


_ENRICHMENT_PREAMBLE = """\
You are enriching a product feature taxonomy with code paths from the codebase.

You will receive products one at a time in the same conversation.
Keep track of what products and features you already returned.
It is fine to return an already-seen product again with extra features or code paths if later turns reveal them.

The codebase is available on disk. Use file search, grep, and code reading to find where each
product and feature is implemented.

## Rules

1. For each input product, decide whether it should stay one product, expand with additional
   features, or split into multiple products based on the codebase structure.
2. Prefer **durable, semantically meaningful glob patterns** over individual files or overly
   generic shared folders:
   - Good: `products/experiments/backend/*`, `frontend/src/scenes/experiments/*`
   - Bad: `products/experiments/backend/models.py`, `products/experiments/backend/api.py`, ...
3. Product `code_paths` should capture stable roots for the area. Feature `code_paths` should be
   narrower and product-specific when distinct ownership exists.
4. Include both backend and frontend paths when they exist.
5. Start by exploring the top-level directory structure to understand how the codebase is organized.
   Look for product-specific directories, feature modules, and shared code.
6. If a feature listed under a product is actually implemented as a **separate product**
   in the codebase (has its own dedicated directory), promote it: return it as a separate
   product entry in the output list, and do not keep it nested under the parent in this turn.
7. If the code clearly shows missing features or nearby products that belong with this area,
   it is okay to add them now. Only add them when the code ownership is clear and the concept is
   genuinely product-facing.
8. Keep names consistent with products already returned earlier in the conversation.
   If this turn reveals more detail for an already-returned product, return that product again
   with the additions.
9. If a feature has no distinct code path (it's part of the parent product's code), set its
   code_paths to an empty list.
10. Do NOT guess paths — verify them by listing or searching the filesystem."""

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

## Already returned in this session

{existing_products}

Keep names consistent with the products above.
If this turn reveals more code paths or missing features for an already-returned product,
return that product again with the additions.

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
    domain: str,
    repository: str,
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

    enriched_file = _enriched_taxonomy_file(domain)
    if enriched_file.exists():
        cached = EnrichedTaxonomy.model_validate_json(enriched_file.read_text())
        if output_fn:
            total_features = sum(len(p.features) for p in cached.products)
            output_fn(f"Using cached enriched taxonomy: {len(cached.products)} products, {total_features} features")
        return cached

    total = len(taxonomy.products)
    if total == 0:
        raise ValueError("No products in taxonomy to enrich")

    if output_fn:
        output_fn(f"Starting multi-turn enrichment: {total} product(s)")

    context = await sync_to_async(resolve_sandbox_context_for_local_dev)(repository)
    output_schema = json.dumps(EnrichedProductTurnOutput.model_json_schema(), indent=2)
    accumulator = EnrichedTaxonomyAccumulator()

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

    accumulator.add_products(list(first_result.products))
    if output_fn:
        output_fn(
            f"Product 1/{total} done: {first_product.name} -> {len(first_result.products)} "
            f"product(s), {len(accumulator.products)} canonical so far"
        )

    # Turns 2..N
    for i, product in enumerate(taxonomy.products[1:], start=2):
        if output_fn:
            output_fn(f"Enriching product {i}/{total}: {product.name}...")

        followup_prompt = _ENRICHMENT_FOLLOWUP_PROMPT.format(
            index=i,
            total_products=total,
            existing_products=accumulator.format_existing_products(),
            product_json=product.model_dump_json(indent=2),
            output_schema=output_schema,
        )

        result = await send_followup(
            session,
            followup_prompt,
            EnrichedProductTurnOutput,
            label=f"product_{i}_of_{total}",
        )

        accumulator.add_products(result.products)
        if output_fn:
            output_fn(
                f"Product {i}/{total} done: {product.name} -> {len(result.products)} "
                f"product(s), {len(accumulator.products)} canonical so far"
            )

    await end_session(session)

    enriched_taxonomy = EnrichedTaxonomy(products=accumulator.products)
    enriched_file.write_text(enriched_taxonomy.model_dump_json(indent=2))

    if output_fn:
        total_features = sum(len(p.features) for p in enriched_taxonomy.products)
        output_fn(f"Enrichment complete: {len(enriched_taxonomy.products)} products, {total_features} features")

    return enriched_taxonomy


def run_enrich_taxonomy(domain: str, repository: str, *, verbose: bool = False, output_fn=None) -> EnrichedTaxonomy:
    taxonomy_result = run_build_taxonomy(domain, repository, verbose=verbose, output_fn=output_fn)
    return asyncio.run(enrich_taxonomy(taxonomy_result, domain, repository, verbose=verbose, output_fn=output_fn))
