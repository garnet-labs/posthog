from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.contextualize import run_contextualize_taxonomy


class Command(BaseCommand):
    help = (
        "Attach routes, scenes, endpoints, and PostHog events from the product context index to the enriched taxonomy"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "domain",
            type=str,
            help="Domain to contextualize taxonomy for (e.g. posthog.com)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild the contextualized taxonomy even if the cached output already exists",
        )

    def handle(self, *args, **options):
        domain = options["domain"]
        contextualized = run_contextualize_taxonomy(domain, force=options["force"], output_fn=self.stdout.write)

        self.stdout.write("")
        for product in contextualized.products:
            feature_matches = sum(
                1
                for feature in product.features
                if feature.url_patterns or feature.api_endpoints or feature.posthog_events
            )
            self.stdout.write(
                self.style.SUCCESS(f"{product.name}") + f" — {len(product.url_patterns)} routes, "
                f"{len(product.api_endpoints)} endpoints, "
                f"{len(product.posthog_events)} events, "
                f"{feature_matches} contextualized features"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"{contextualized.stats.feature_matches} feature matches, "
                f"{contextualized.stats.product_matches} product matches, "
                f"{len(contextualized.stats.ambiguous_entries)} ambiguous, "
                f"{len(contextualized.stats.unmatched_entries)} unmatched."
            )
        )
