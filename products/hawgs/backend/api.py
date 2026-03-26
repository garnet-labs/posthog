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


class ProductTaxonomyViewSet(TeamAndOrgViewSetMixin, viewsets.ViewSet):
    scope_object = "INTERNAL"

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
