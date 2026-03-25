from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.crawl import crawl_website


class Command(BaseCommand):
    help = "Crawl a website's product pages and cache results as JSON files for feature extraction"

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            type=str,
            help="Homepage URL of the website to crawl (e.g. posthog.com)",
        )

    def handle(self, *args, **options):
        url = options["url"]
        self.stdout.write(f"Crawling {url}...")
        pages = crawl_website(url)
        self.stdout.write(self.style.SUCCESS(f"Done. {len(pages)} pages available."))
