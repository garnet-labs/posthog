# Hawgs website taxonomy pipeline

Builds a cached map from a marketing site to PostHog product areas.
The output is meant to give agents fast product context for PR analysis and future memory/lookup workflows:
which product area a code path belongs to,
which public pages describe it,
and which neighboring features are likely affected.

## Pipeline commands (run in order)

All cache is per-domain under `crawl/crawl_cache/<domain>/`.

```bash
# 1. Crawl — discover product pages from sitemap, then scrape them
python manage.py crawl_website posthog.com

# 2. Build taxonomy — extract hierarchical product/feature taxonomy from scraped pages
python manage.py build_taxonomy posthog.com --repository PostHog/posthog

# 3. Enrich — add code paths to the taxonomy via multi-turn sandbox agent
python manage.py enrich_taxonomy posthog.com --repository PostHog/posthog

# 4. Contextualize — attach routes, API endpoints, and PostHog events
python manage.py contextualize_taxonomy posthog.com

# 5. Lookup — query which product/feature a code path belongs to
python manage.py lookup_taxonomy_path posthog.com <code_path>
```

Steps 2-4 are cache-first: they skip if the output file already exists.
Delete the relevant `_*.json` file under `crawl_cache/<domain>/` to force a re-run.

### Step details

1. **`crawl_website <url>`** — uses a sandbox agent to inspect sitemap URLs only,
   writes `_selected_urls.json`, then batch-scrapes the selected URLs with Firecrawl.
   The homepage is automatically included. Stores one JSON per page (markdown, summary, screenshot, metadata).
   Only scrapes URLs not already cached.
2. **`build_taxonomy <domain> --repository <org/repo>`** — reads cached page JSON files,
   sends all page content to a sandbox agent with the target repository cloned, writes `_taxonomy.json`.
   Output: `products[] -> features[]`, each with description and `source_urls`.
3. **`enrich_taxonomy <domain> --repository <org/repo>`** — builds taxonomy if needed,
   then runs a multi-turn sandbox agent over each product in one conversation. Writes `_enriched_taxonomy.json`.
   Adds `code_paths` (directory-level globs), may promote features to products, may add
   missing products/features when code structure is more explicit than the website.
4. **`contextualize_taxonomy <domain>`** — reads `_enriched_taxonomy.json` and
   `_product-context-index.json`, writes `_contextualized_taxonomy.json`.
   Attaches route patterns, API endpoints, and PostHog events.
   Matching is conservative: prefer `page_component`, then widen to `key_files`;
   feature-level only on unique matches, otherwise product-level.
5. **`lookup_taxonomy_path <code_path>`** — reads `_contextualized_taxonomy.json`,
   matches the input path against product/feature `code_paths`.
   Prefers feature matches over broader product matches.

## Artifacts

All under `crawl/crawl_cache/<domain>/`:

- `_selected_urls.json`: sitemap-derived candidate product page URLs
- `<url-slug>.json`: scraped page cache with `markdown`, `summary`, `screenshot`, and `metadata`
- `_taxonomy.json`: website-grounded product/feature taxonomy
- `_enriched_taxonomy.json`: taxonomy plus verified code paths
- `_product-context-index.json`: scene-level runtime/frontend index from the separate context-indexing tool
- `_contextualized_taxonomy.json`: enriched taxonomy plus matched routes, API endpoints, and PostHog events

## Working rules

- The crawl step is intentionally sitemap-first and excludes docs, blog, pricing, legal, support, and other non-product content.
- Use the website's own product and feature names; do not invent a new taxonomy unless the implementation clearly forces a promotion during enrichment.
- Enrichment is multi-turn in one sandbox conversation. Reuse product names consistently across turns and prefer expanding/splitting an existing area over inventing duplicate labels.
- `code_paths` should be verified on disk and should prefer durable, product-specific directory globs over long file lists.
- Treat `_product-context-index.json` as a route/scene index, not as a source of truth for product hierarchy. Use it to attach operational context onto the taxonomy, not to replace the taxonomy.
- Contextualization should stay conservative. Only attach feature-level context on unique matches; if the scene spans multiple features but clearly belongs to one product, attach it at product level instead.
- Path lookup should treat `_contextualized_taxonomy.json` as the read-only lookup DB. Prefer the most specific matching `code_paths` pattern, and prefer feature matches over broader product matches.
- The pipeline is cache-first. If you change discovery rules, prompt logic, schemas, or enrichment heuristics, delete the affected cache files before rerunning or you will get stale results.
- This directory now has a local command-level path lookup. A real HTTP/API layer for external callers is still future work.
- `crawl_website` requires `FIRECRAWL_API_KEY`. Discovery uses a dummy repo (`PostHog/.github`).
  Taxonomy and enrichment require `--repository` pointing to the target codebase's GitHub repo
  and depend on the sandbox agent helpers in `products.tasks.backend.services.custom_prompt_*`.

## Future notes

- A periodic refresh/self-healing loop for rerunning crawl/build/enrich is still future work.
- A real API endpoint around the local lookup command is still future work.

## Maintaining this file

If the pipeline stages, cache layout, artifact schemas, enrichment rules, or the eventual lookup API change,
update this AGENTS.md to match the new architecture.
