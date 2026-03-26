import json
from datetime import UTC, datetime
from pathlib import Path

from rest_framework import serializers, viewsets
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin

CRAWL_CACHE_DIR = Path(__file__).parent / "crawl" / "crawl_cache"


class AnalyzedSiteSerializer(serializers.Serializer):
    domain = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    screenshot = serializers.URLField(allow_null=True)
    last_updated = serializers.DateTimeField(allow_null=True)
    products_count = serializers.IntegerField()
    features_count = serializers.IntegerField()
    pages_count = serializers.IntegerField()


def _build_url_to_taxonomy_map(enriched_file: Path) -> dict[str, list[dict]]:
    """Build a map from source_url -> list of {type, name} for products and features."""
    url_map: dict[str, list[dict]] = {}
    with open(enriched_file) as f:
        taxonomy = json.load(f)
    for product in taxonomy.get("products", []):
        for url in product.get("source_urls", []):
            url_map.setdefault(url, []).append({"type": "product", "name": product["name"]})
        for feature in product.get("features", []):
            for url in feature.get("source_urls", []):
                url_map.setdefault(url, []).append({"type": "feature", "name": feature["name"]})
                # always include the parent product when a feature matches
                url_map[url].append({"type": "product", "name": product["name"]})
    return url_map


class ProductTaxonomyViewSet(TeamAndOrgViewSetMixin, viewsets.ViewSet):
    scope_object = "INTERNAL"
    lookup_value_regex = r"[^/]+"  # allow dots in domain names

    def retrieve(self, request, *args, **kwargs):
        domain = kwargs.get("pk", "")
        domain_dir = CRAWL_CACHE_DIR / domain

        if not domain_dir.is_dir():
            return Response({"detail": "Not found"}, status=404)

        enriched_file = domain_dir / "_enriched_taxonomy.json"
        if not enriched_file.exists():
            return Response({"detail": "Not found"}, status=404)

        url_map = _build_url_to_taxonomy_map(enriched_file)

        pages = []
        for page_file in sorted(domain_dir.iterdir()):
            if not page_file.suffix == ".json" or page_file.name.startswith("_"):
                continue

            with open(page_file) as f:
                page_data = json.load(f)

            metadata = page_data.get("metadata", {})
            page_url = metadata.get("source_url") or metadata.get("url") or ""

            # Find related products/features via source_url matching
            related = url_map.get(page_url, [])
            related_products = sorted({r["name"] for r in related if r["type"] == "product"})
            related_features = sorted({r["name"] for r in related if r["type"] == "feature"})

            last_updated = None
            try:
                mtime = page_file.stat().st_mtime
                last_updated = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
            except OSError:
                pass

            pages.append(
                {
                    "url": page_url,
                    "title": metadata.get("title") or metadata.get("og_title") or page_file.stem,
                    "description": metadata.get("description") or metadata.get("og_description") or "",
                    "summary": page_data.get("summary", ""),
                    "screenshot": page_data.get("screenshot"),
                    "last_updated": last_updated,
                    "related_products": related_products,
                    "related_features": related_features,
                }
            )

        return Response({"domain": domain, "pages": pages})

    def list(self, request, *args, **kwargs):
        sites = []

        if not CRAWL_CACHE_DIR.exists():
            return Response({"results": []})

        for domain_dir in sorted(CRAWL_CACHE_DIR.iterdir()):
            if not domain_dir.is_dir():
                continue

            enriched_file = domain_dir / "_enriched_taxonomy.json"
            if not enriched_file.exists():
                continue

            domain = domain_dir.name

            # Read main page JSON for summary/screenshot
            main_page_file = domain_dir / f"{domain}.json"
            title = domain
            description = ""
            screenshot = None

            if main_page_file.exists():
                with open(main_page_file) as f:
                    main_page = json.load(f)
                    screenshot = main_page.get("screenshot")
                    metadata = main_page.get("metadata", {})
                    title = metadata.get("title") or metadata.get("og_title") or domain
                    description = metadata.get("description") or metadata.get("og_description") or ""

            # Read enriched taxonomy for product/feature counts
            with open(enriched_file) as f:
                taxonomy = json.load(f)
                products = taxonomy.get("products", [])
                products_count = len(products)
                features_count = sum(len(p.get("features", [])) for p in products)

            # Count page files (non-underscore prefixed .json files)
            pages_count = sum(1 for f in domain_dir.iterdir() if f.suffix == ".json" and not f.name.startswith("_"))

            # Last updated from most recent file modification time
            last_updated = None
            try:
                latest = max(
                    (f.stat().st_mtime for f in domain_dir.iterdir() if f.is_file()),
                    default=None,
                )
                if latest:
                    last_updated = datetime.fromtimestamp(latest, tz=UTC).isoformat()
            except (OSError, ValueError):
                pass

            sites.append(
                {
                    "domain": domain,
                    "title": title,
                    "description": description,
                    "screenshot": screenshot,
                    "last_updated": last_updated,
                    "products_count": products_count,
                    "features_count": features_count,
                    "pages_count": pages_count,
                }
            )

        return Response({"results": sites})
