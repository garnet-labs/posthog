# Hawgs website taxonomy pipeline

Builds a cached map from a marketing site to PostHog product areas.
The output is meant to give agents fast product context for PR analysis and future memory/lookup workflows:
which product area a code path belongs to,
which public pages describe it,
and which neighboring features are likely affected.

## Current flow

1. `python manage.py crawl_website <url>`
   - Uses a sandbox agent to inspect sitemap URLs only and writes `crawl/crawl_cache/_selected_urls.json`
   - Filters for product, feature, platform, integration, and use-case pages
   - Scrapes the selected URLs with Firecrawl and stores one JSON file per page in `crawl/crawl_cache/`
2. `python manage.py build_taxonomy`
   - Reads the cached page JSON files and writes `crawl/crawl_cache/_taxonomy.json`
   - Output shape: `products[] -> features[]`, each with a concise description and `source_urls`
3. `python manage.py enrich_taxonomy`
   - Reuses or builds the taxonomy, then runs a multi-turn agent over each product in the same conversation
   - Writes `crawl/crawl_cache/_enriched_taxonomy.json`
   - Adds `code_paths` to products and features, may promote a feature into its own product, and may add clearly missing nearby products/features when the code structure is more explicit than the website taxonomy
4. `python manage.py contextualize_taxonomy`
   - Reads `crawl/crawl_cache/_enriched_taxonomy.json` and `crawl/crawl_cache/_product-context-index.json`
   - Writes `crawl/crawl_cache/_contextualized_taxonomy.json`
   - Attaches safe runtime/frontend context to products and features: route patterns, API endpoints, and PostHog events
   - Matching is conservative: prefer `page_component`, then widen to `key_files`; attach at feature level only for unique feature matches, otherwise fall back to unique product matches
5. `python manage.py lookup_taxonomy_path <code_path>`
   - Reads `crawl/crawl_cache/_contextualized_taxonomy.json`
   - Matches the input repo path against product/feature `code_paths`
   - Prefers feature matches over broader product-root matches and returns the matched taxonomy node plus attached routes/endpoints/events

## Artifacts

- `crawl/crawl_cache/_selected_urls.json`: sitemap-derived candidate product pages
- `crawl/crawl_cache/<url-slug>.json`: scraped page cache with `markdown`, `screenshot`, and `metadata`
- `crawl/crawl_cache/_taxonomy.json`: website-grounded product/feature taxonomy
- `crawl/crawl_cache/_enriched_taxonomy.json`: taxonomy plus verified code paths
- `crawl/crawl_cache/_product-context-index.json`: scene-level runtime/frontend index from the separate context-indexing tool
- `crawl/crawl_cache/_contextualized_taxonomy.json`: enriched taxonomy plus matched routes, API endpoints, and PostHog events

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
- `crawl_website` requires `FIRECRAWL_API_KEY`. Discovery, taxonomy, and enrichment also depend on the sandbox agent helpers in `products.tasks.backend.services.custom_prompt_*`.

## Future notes

- A periodic refresh/self-healing loop for rerunning crawl/build/enrich is still future work.
- A real API endpoint around the local lookup command is still future work.

## Maintaining this file

If the pipeline stages, cache layout, artifact schemas, enrichment rules, or the eventual lookup API change,
update this AGENTS.md to match the new architecture.
