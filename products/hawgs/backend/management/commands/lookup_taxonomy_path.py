from django.core.management.base import BaseCommand

from products.hawgs.backend.crawl.lookup import lookup_code_path


class Command(BaseCommand):
    help = "Look up which product or feature a code path belongs to using the contextualized taxonomy"

    def add_arguments(self, parser):
        parser.add_argument(
            "code_path",
            type=str,
            help="Repo-relative or absolute code path to look up",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the lookup result as JSON",
        )

    def handle(self, *args, **options):
        result = lookup_code_path(options["code_path"])

        if options["json"]:
            self.stdout.write(result.model_dump_json(indent=2))
            return

        if not result.matches:
            self.stdout.write(self.style.WARNING(f"No taxonomy match for {result.code_path}"))
            return

        for match in result.matches:
            label = (
                match.product_name if match.feature_name is None else f"{match.product_name} -> {match.feature_name}"
            )
            self.stdout.write(self.style.SUCCESS(label) + f" [{match.match_level}]")
            self.stdout.write(f"  matched pattern: {match.matched_pattern}")
            if match.url_patterns:
                self.stdout.write(f"  routes: {', '.join(match.url_patterns)}")
            if match.api_endpoints:
                self.stdout.write(f"  endpoints: {', '.join(match.api_endpoints[:5])}")
            if match.posthog_events:
                self.stdout.write(f"  events: {', '.join(match.posthog_events[:5])}")
