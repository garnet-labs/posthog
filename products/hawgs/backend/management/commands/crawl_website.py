from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.crawl import crawl_website


class Command(BaseCommand):
    help = "Discover product pages via sitemap analysis, then scrape them with Firecrawl"

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            type=str,
            help="Homepage URL of the website to crawl (e.g. posthog.com)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Stream all raw agent log lines during URL discovery",
        )

    def handle(self, *args, **options):
        url = options["url"]
        verbose = options["verbose"]
        pages = crawl_website(url, verbose=verbose, output_fn=self.stdout.write)
        self.stdout.write(self.style.SUCCESS(f"Done. {len(pages)} pages available."))
