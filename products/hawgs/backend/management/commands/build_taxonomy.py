from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.taxonomy import run_build_taxonomy


class Command(BaseCommand):
    help = "Build a hierarchical feature taxonomy from crawled product pages"

    def add_arguments(self, parser):
        parser.add_argument(
            "domain",
            type=str,
            help="Domain to build taxonomy for (e.g. posthog.com)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Stream all raw agent log lines",
        )

    def handle(self, *args, **options):
        domain = options["domain"]
        verbose = options["verbose"]
        taxonomy = run_build_taxonomy(domain, verbose=verbose, output_fn=self.stdout.write)

        self.stdout.write("")
        for product in taxonomy.products:
            self.stdout.write(self.style.SUCCESS(f"{product.name}") + f" — {product.description}")
            for feature in product.features:
                self.stdout.write(f"  - {feature.name}: {feature.description}")
        self.stdout.write("")
        total_features = sum(len(p.features) for p in taxonomy.products)
        self.stdout.write(self.style.SUCCESS(f"Done. {len(taxonomy.products)} products, {total_features} features."))
