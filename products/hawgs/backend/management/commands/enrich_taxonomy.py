from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.taxonomy import run_enrich_taxonomy


class Command(BaseCommand):
    help = "Enrich the feature taxonomy with code paths from the codebase via multi-turn agent"

    def add_arguments(self, parser):
        parser.add_argument(
            "domain",
            type=str,
            help="Domain to enrich taxonomy for (e.g. posthog.com)",
        )
        parser.add_argument(
            "--repository",
            type=str,
            required=True,
            help="GitHub repository in org/repo format (e.g. PostHog/posthog)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Stream all raw agent log lines",
        )

    def handle(self, *args, **options):
        domain = options["domain"]
        repository = options["repository"]
        verbose = options["verbose"]
        enriched = run_enrich_taxonomy(domain, repository, verbose=verbose, output_fn=self.stdout.write)

        self.stdout.write("")
        for product in enriched.products:
            self.stdout.write(self.style.SUCCESS(f"{product.name}") + f" — {product.description}")
            for path in product.code_paths:
                self.stdout.write(f"    [{path}]")
            for feature in product.features:
                self.stdout.write(f"  - {feature.name}: {feature.description}")
                for path in feature.code_paths:
                    self.stdout.write(f"      [{path}]")

        self.stdout.write("")
        total_features = sum(len(p.features) for p in enriched.products)
        self.stdout.write(self.style.SUCCESS(f"Done. {len(enriched.products)} products, {total_features} features."))
