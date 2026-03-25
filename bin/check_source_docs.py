#!/usr/bin/env python3
# ruff: noqa: T201
"""Check that every registered ExternalDataSourceType has a corresponding doc page.

Usage:
    python bin/check_source_docs.py              # check and report
    python bin/check_source_docs.py --generate   # generate stubs for missing sources

Exit code 0 if all sources have docs, 1 if any are missing.
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path

TYPES_FILE = Path("products/data_warehouse/backend/types.py")
DOCS_DIR = Path("docs/published/docs/cdp/sources")
SNIPPETS_DIR = DOCS_DIR / "_snippets"

# Explicit slug overrides for sources where the automatic derivation doesn't match
# the established URL pattern. Keyed by the ExternalDataSourceType value (first string
# in the TextChoices tuple).
SLUG_OVERRIDES: dict[str, str] = {
    # From existing docsUrl values
    "BigQuery": "bigquery",
    "MongoDB": "mongodb",
    "MSSQL": "azure-db",
    "MySQL": "mysql",
    "TemporalIO": "temporal",
    "DoIt": "doit",
    "TikTokAds": "tiktok-ads",
    # Brand names that are single compound words
    "BuildBetter": "buildbetter",
    "CustomerIO": "customerio",
    "SFTP": "sftp",
    "DynamoDB": "dynamodb",
    "CockroachDB": "cockroachdb",
    "CircleCI": "circleci",
    "Auth0": "auth0",
    "GitLab": "gitlab",
    "PayPal": "paypal",
    "NetSuite": "netsuite",
    "QuickBooks": "quickbooks",
    "FullStory": "fullstory",
    "BigCommerce": "bigcommerce",
    "WooCommerce": "woocommerce",
    "OneDrive": "onedrive",
    "SharePoint": "sharepoint",
    "LaunchDarkly": "launchdarkly",
    "HelpScout": "helpscout",
    "SalesLoft": "salesloft",
    "SendGrid": "sendgrid",
    "SurveyMonkey": "surveymonkey",
    "ChartMogul": "chartmogul",
    "ConvertKit": "convertkit",
    "MailerLite": "mailerlite",
    "RingCentral": "ringcentral",
    "ServiceNow": "servicenow",
    "PagerDuty": "pagerduty",
    "RevenueCat": "revenuecat",
    "AppsFlyer": "appsflyer",
    "ActiveCampaign": "activecampaign",
    "CampaignMonitor": "campaignmonitor",
    "YouTubeAnalytics": "youtube-analytics",
    "FacebookPages": "facebook-pages",
    "ZohoCRM": "zoho-crm",
    "BambooHR": "bamboo-hr",
    "ClickUp": "clickup",
    "MicrosoftTeams": "microsoft-teams",
    "GoogleDrive": "google-drive",
    "GoogleAnalytics": "google-analytics",
}


def camel_to_kebab(name: str) -> str:
    """Convert CamelCase to kebab-case.

    Handles sequences of uppercase letters (e.g., "GoogleAds" -> "google-ads",
    "BambooHR" -> "bamboo-hr").
    """
    # Insert hyphen between a lowercase/digit and an uppercase letter
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    # Insert hyphen between consecutive uppercase letters followed by lowercase
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    return s.lower()


def source_to_slug(source_value: str) -> str:
    """Convert an ExternalDataSourceType value to a doc slug."""
    if source_value in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[source_value]
    return camel_to_kebab(source_value)


def parse_source_types() -> list[str]:
    """Parse ExternalDataSourceType enum values from types.py."""
    content = TYPES_FILE.read_text()

    # Extract only the ExternalDataSourceType class body
    match = re.search(
        r"class ExternalDataSourceType\(.*?\):\s*\n(.*?)(?:\nclass |\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        print(f"ERROR: ExternalDataSourceType class not found in {TYPES_FILE}", file=sys.stderr)
        sys.exit(2)

    class_body = match.group(1)
    # Match lines like: STRIPE = "Stripe", "Stripe"
    pattern = re.compile(r'^\s+\w+\s*=\s*"([^"]+)",\s*"[^"]+"', re.MULTILINE)
    values = pattern.findall(class_body)
    if not values:
        print(f"ERROR: No enum values found in ExternalDataSourceType", file=sys.stderr)
        sys.exit(2)
    return values


def find_doc_file(slug: str) -> Path | None:
    """Check if a doc file exists for the given slug."""
    path = DOCS_DIR / f"{slug}.mdx"
    if path.exists():
        return path
    return None


def human_readable_label(source_value: str) -> str:
    """Convert a source value to a human-readable label for doc titles."""
    # Insert spaces in CamelCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", source_value)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return s


def generate_stub(source_value: str, slug: str) -> None:
    """Generate a stub doc page and snippet for a source."""
    label = human_readable_label(source_value)
    # Sanitize component name for MDX import (remove spaces, hyphens)
    component_name = re.sub(r"[^a-zA-Z0-9]", "", f"Source{source_value}")

    page_content = f"""---
title: Linking {label} as a source
sidebar: Docs
showTitle: true
availability:
    free: full
    selfServe: full
    enterprise: full
---

import {component_name} from './_snippets/source-{slug}.mdx'

<{component_name} />
"""

    snippet_content = f"""> **{label}** as a data warehouse source is coming soon.
>
> Check the [sources overview](/docs/cdp/sources) for currently available sources.
"""

    page_path = DOCS_DIR / f"{slug}.mdx"
    snippet_path = SNIPPETS_DIR / f"source-{slug}.mdx"

    page_path.write_text(page_content)
    snippet_path.write_text(snippet_content)
    print(f"  CREATED {page_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate stub docs for missing sources",
    )
    args = parser.parse_args()

    source_values = parse_source_types()
    print(f"Found {len(source_values)} source types in {TYPES_FILE}")

    missing: list[tuple[str, str]] = []
    found = 0

    for value in source_values:
        slug = source_to_slug(value)
        doc = find_doc_file(slug)
        if doc:
            found += 1
        else:
            missing.append((value, slug))

    print(f"  {found} sources have docs")
    print(f"  {len(missing)} sources are missing docs")

    if missing:
        print("\nMissing docs:")
        for value, slug in sorted(missing, key=lambda x: x[1]):
            print(f"  - {value} (expected: {slug}.mdx)")

        if args.generate:
            print("\nGenerating stubs...")
            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
            for value, slug in missing:
                generate_stub(value, slug)
            print(f"\nGenerated {len(missing)} stub pages")
        else:
            print(f"\nRun with --generate to create stub pages")

    if missing and not args.generate:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
