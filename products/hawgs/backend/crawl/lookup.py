import fnmatch
import posixpath
from pathlib import Path

from pydantic import BaseModel, Field

from products.hawgs.backend.crawl.contextualize import (
    CONTEXTUALIZED_TAXONOMY_FILE,
    ContextApiEndpoint,
    ContextPostHogEvent,
    ContextualizedTaxonomy,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class CodePathLookupMatch(BaseModel):
    match_level: str = Field(description="Either 'feature' or 'product'")
    product_name: str = Field(description="Matched product name")
    product_description: str = Field(description="Matched product description")
    feature_name: str | None = Field(default=None, description="Matched feature name if this is a feature-level match")
    feature_description: str | None = Field(
        default=None,
        description="Matched feature description if this is a feature-level match",
    )
    matched_pattern: str = Field(description="Pattern from the taxonomy that matched the input path")
    url_patterns: list[str] = Field(default_factory=list, description="Route patterns attached to the matched node")
    api_endpoints: list[str] = Field(
        default_factory=list, description="Attached API endpoints as 'METHOD path' strings"
    )
    posthog_events: list[str] = Field(default_factory=list, description="Attached PostHog event names")


class CodePathLookupResult(BaseModel):
    code_path: str = Field(description="Normalized repo-relative code path used for matching")
    matches: list[CodePathLookupMatch] = Field(description="Best taxonomy matches for the code path")


def _normalize_code_path(code_path: str) -> str:
    candidate = Path(code_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            return resolved.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return resolved.as_posix()

    return posixpath.normpath(code_path.replace("\\", "/"))


def _pattern_sort_key(pattern: str) -> tuple[int, int, int]:
    return (0 if "*" in pattern else 1, pattern.count("/"), len(pattern.replace("*", "")))


def _best_matching_pattern(code_path: str, patterns: list[str]) -> str | None:
    matching_patterns = [pattern for pattern in patterns if fnmatch.fnmatch(code_path, pattern)]
    if not matching_patterns:
        return None

    return max(matching_patterns, key=_pattern_sort_key)


def _format_api_endpoints(api_endpoints: list[ContextApiEndpoint]) -> list[str]:
    return [f"{api_endpoint.method} {api_endpoint.path}" for api_endpoint in api_endpoints]


def _format_posthog_events(posthog_events: list[ContextPostHogEvent]) -> list[str]:
    return [posthog_event.event_name for posthog_event in posthog_events]


def _load_contextualized_taxonomy() -> ContextualizedTaxonomy:
    if not CONTEXTUALIZED_TAXONOMY_FILE.exists():
        raise RuntimeError(
            f"Missing contextualized taxonomy at {CONTEXTUALIZED_TAXONOMY_FILE}. "
            "Run `python manage.py contextualize_taxonomy` first."
        )

    return ContextualizedTaxonomy.model_validate_json(CONTEXTUALIZED_TAXONOMY_FILE.read_text())


def lookup_code_path(code_path: str) -> CodePathLookupResult:
    normalized_code_path = _normalize_code_path(code_path)
    taxonomy = _load_contextualized_taxonomy()

    feature_matches: list[CodePathLookupMatch] = []
    product_matches: list[CodePathLookupMatch] = []

    for product in taxonomy.products:
        for feature in product.features:
            matched_pattern = _best_matching_pattern(normalized_code_path, feature.code_paths)
            if matched_pattern is None:
                continue

            feature_matches.append(
                CodePathLookupMatch(
                    match_level="feature",
                    product_name=product.name,
                    product_description=product.description,
                    feature_name=feature.name,
                    feature_description=feature.description,
                    matched_pattern=matched_pattern,
                    url_patterns=feature.url_patterns,
                    api_endpoints=_format_api_endpoints(feature.api_endpoints),
                    posthog_events=_format_posthog_events(feature.posthog_events),
                )
            )

        matched_pattern = _best_matching_pattern(normalized_code_path, product.code_paths)
        if matched_pattern is None:
            continue

        product_matches.append(
            CodePathLookupMatch(
                match_level="product",
                product_name=product.name,
                product_description=product.description,
                matched_pattern=matched_pattern,
                url_patterns=product.url_patterns,
                api_endpoints=_format_api_endpoints(product.api_endpoints),
                posthog_events=_format_posthog_events(product.posthog_events),
            )
        )

    matches = feature_matches if feature_matches else product_matches
    matches.sort(key=lambda match: _pattern_sort_key(match.matched_pattern), reverse=True)

    return CodePathLookupResult(code_path=normalized_code_path, matches=matches)
