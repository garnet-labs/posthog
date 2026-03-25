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
   - Reuses or builds the taxonomy, then runs a multi-turn agent over each product
   - Writes `crawl/crawl_cache/_enriched_taxonomy.json`
   - Adds `code_paths` to products and features, and may promote a feature into its own product if the codebase is organized that way

## Artifacts

- `crawl/crawl_cache/_selected_urls.json`: sitemap-derived candidate product pages
- `crawl/crawl_cache/<url-slug>.json`: scraped page cache with `markdown`, `screenshot`, and `metadata`
- `crawl/crawl_cache/_taxonomy.json`: website-grounded product/feature taxonomy
- `crawl/crawl_cache/_enriched_taxonomy.json`: taxonomy plus verified code paths

## Working rules

- The crawl step is intentionally sitemap-first and excludes docs, blog, pricing, legal, support, and other non-product content.
- Use the website's own product and feature names; do not invent a new taxonomy unless the implementation clearly forces a promotion during enrichment.
- `code_paths` should be verified on disk and should prefer stable directory globs over long file lists.
- The pipeline is cache-first. If you change discovery rules, prompt logic, schemas, or enrichment heuristics, delete the affected cache files before rerunning or you will get stale results.
- This directory does not yet contain the final "code path -> product/feature" API. `_enriched_taxonomy.json` is the current handoff artifact for that future lookup layer.
- `crawl_website` requires `FIRECRAWL_API_KEY`. Discovery, taxonomy, and enrichment also depend on the sandbox agent helpers in `products.tasks.backend.services.custom_prompt_*`.

## Maintaining this file

If the pipeline stages, cache layout, artifact schemas, enrichment rules, or the eventual lookup API change,
update this AGENTS.md to match the new architecture.
