import json
import fnmatch
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from products.hawgs.backend.crawl.crawl import cache_dir_for_domain
from products.hawgs.backend.crawl.taxonomy import (
    EnrichedFeature,
    EnrichedProduct,
    EnrichedTaxonomy,
    _enriched_taxonomy_file,
)

logger = logging.getLogger(__name__)


class ContextIndexApiEndpoint(BaseModel):
    path: str
    method: str
    source_file: str | None = None


class ContextIndexPostHogEvent(BaseModel):
    event_name: str
    source_file: str | None = None


class ContextIndexEntry(BaseModel):
    url_pattern: str | None = None
    scene: str | None = None
    page_component: str | None = None
    key_files: list[str] = Field(default_factory=list)
    api_endpoints: list[ContextIndexApiEndpoint] = Field(default_factory=list)
    posthog_events: list[ContextIndexPostHogEvent] = Field(default_factory=list)


class ContextApiEndpoint(BaseModel):
    path: str = Field(description="API path used by this product area")
    method: str = Field(description="HTTP method")
    source_files: list[str] = Field(description="Frontend files where this endpoint call was found")
    context_entries: list[str] = Field(description="Context index entries that referenced this endpoint")


class ContextPostHogEvent(BaseModel):
    event_name: str = Field(description="Captured PostHog event name")
    source_files: list[str] = Field(description="Frontend files where this event was found")
    context_entries: list[str] = Field(description="Context index entries that referenced this event")


class ContextualizedFeature(EnrichedFeature):
    url_patterns: list[str] = Field(default_factory=list, description="Frontend route patterns mapped to this feature")
    api_endpoints: list[ContextApiEndpoint] = Field(
        default_factory=list,
        description="API endpoints referenced by matched frontend scenes",
    )
    posthog_events: list[ContextPostHogEvent] = Field(
        default_factory=list,
        description="Captured PostHog events referenced by matched frontend scenes",
    )


class ContextualizedProduct(EnrichedProduct):
    url_patterns: list[str] = Field(default_factory=list, description="Frontend route patterns mapped to this product")
    api_endpoints: list[ContextApiEndpoint] = Field(
        default_factory=list,
        description="API endpoints referenced by matched frontend scenes",
    )
    posthog_events: list[ContextPostHogEvent] = Field(
        default_factory=list,
        description="Captured PostHog events referenced by matched frontend scenes",
    )
    features: list[ContextualizedFeature] = Field(
        description="Features within this product, each with optional runtime/frontend context",
    )


class ContextualizationStats(BaseModel):
    total_context_entries: int = Field(description="Number of entries in _product-context-index.json")
    feature_matches: int = Field(description="Entries attached at feature level")
    product_matches: int = Field(description="Entries attached at product level")
    page_component_matches: int = Field(description="Entries matched by page_component only")
    page_plus_key_file_matches: int = Field(description="Entries matched after widening to key_files")
    ambiguous_entries: list[str] = Field(default_factory=list, description="Entries skipped due to ambiguous matches")
    unmatched_entries: list[str] = Field(default_factory=list, description="Entries skipped due to no taxonomy match")


class ContextualizedTaxonomy(BaseModel):
    products: list[ContextualizedProduct] = Field(description="Enriched taxonomy with runtime/frontend context")
    stats: ContextualizationStats = Field(description="Matching statistics for the context-index join step")


@dataclass
class _ContextApiEndpointAccumulator:
    method: str
    path: str
    source_files: set[str] = field(default_factory=set)
    context_entries: set[str] = field(default_factory=set)

    def add_reference(self, context_entry: str, source_file: str | None) -> None:
        self.context_entries.add(context_entry)
        if source_file:
            self.source_files.add(source_file)

    def build(self) -> ContextApiEndpoint:
        return ContextApiEndpoint(
            path=self.path,
            method=self.method,
            source_files=sorted(self.source_files),
            context_entries=sorted(self.context_entries),
        )


@dataclass
class _ContextPostHogEventAccumulator:
    event_name: str
    source_files: set[str] = field(default_factory=set)
    context_entries: set[str] = field(default_factory=set)

    def add_reference(self, context_entry: str, source_file: str | None) -> None:
        self.context_entries.add(context_entry)
        if source_file:
            self.source_files.add(source_file)

    def build(self) -> ContextPostHogEvent:
        return ContextPostHogEvent(
            event_name=self.event_name,
            source_files=sorted(self.source_files),
            context_entries=sorted(self.context_entries),
        )


@dataclass
class _ContextAttachmentAccumulator:
    url_patterns: set[str] = field(default_factory=set)
    api_endpoints: dict[tuple[str, str], _ContextApiEndpointAccumulator] = field(default_factory=dict)
    posthog_events: dict[str, _ContextPostHogEventAccumulator] = field(default_factory=dict)

    def add_context_entry(
        self,
        context_entry: str,
        entry: ContextIndexEntry,
    ) -> None:
        if entry.url_pattern:
            self.url_patterns.add(entry.url_pattern)

        for api_endpoint in entry.api_endpoints:
            endpoint_key = (api_endpoint.method, api_endpoint.path)
            accumulator = self.api_endpoints.setdefault(
                endpoint_key,
                _ContextApiEndpointAccumulator(method=api_endpoint.method, path=api_endpoint.path),
            )
            accumulator.add_reference(context_entry, api_endpoint.source_file)

        for posthog_event in entry.posthog_events:
            accumulator = self.posthog_events.setdefault(
                posthog_event.event_name,
                _ContextPostHogEventAccumulator(event_name=posthog_event.event_name),
            )
            accumulator.add_reference(context_entry, posthog_event.source_file)

    def build_kwargs(self) -> dict:
        return {
            "url_patterns": sorted(self.url_patterns),
            "api_endpoints": [self.api_endpoints[key].build() for key in sorted(self.api_endpoints)],
            "posthog_events": [self.posthog_events[key].build() for key in sorted(self.posthog_events)],
        }


@dataclass
class _FeatureAccumulator:
    feature: EnrichedFeature
    context: _ContextAttachmentAccumulator = field(default_factory=_ContextAttachmentAccumulator)

    def build(self) -> ContextualizedFeature:
        return ContextualizedFeature(**self.feature.model_dump(), **self.context.build_kwargs())


@dataclass
class _ProductAccumulator:
    product: EnrichedProduct
    context: _ContextAttachmentAccumulator = field(default_factory=_ContextAttachmentAccumulator)
    feature_accumulators: list[_FeatureAccumulator] = field(init=False)
    feature_by_key: dict[str, _FeatureAccumulator] = field(init=False)

    def __post_init__(self) -> None:
        self.feature_accumulators = [_FeatureAccumulator(feature) for feature in self.product.features]
        self.feature_by_key = {
            ContextualizedTaxonomyBuilder.normalize_name(feature_accumulator.feature.name): feature_accumulator
            for feature_accumulator in self.feature_accumulators
        }

    def build(self) -> ContextualizedProduct:
        product_data = self.product.model_dump()
        product_data.pop("features", None)
        return ContextualizedProduct(
            **product_data,
            **self.context.build_kwargs(),
            features=[feature_accumulator.build() for feature_accumulator in self.feature_accumulators],
        )


@dataclass
class _MatchResult:
    product_keys: set[str] = field(default_factory=set)
    feature_keys: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class _ContextualizationStatsAccumulator:
    total_context_entries: int
    feature_matches: int = 0
    product_matches: int = 0
    page_component_matches: int = 0
    page_plus_key_file_matches: int = 0
    ambiguous_entries: list[str] = field(default_factory=list)
    unmatched_entries: list[str] = field(default_factory=list)

    def build(self) -> ContextualizationStats:
        return ContextualizationStats(
            total_context_entries=self.total_context_entries,
            feature_matches=self.feature_matches,
            product_matches=self.product_matches,
            page_component_matches=self.page_component_matches,
            page_plus_key_file_matches=self.page_plus_key_file_matches,
            ambiguous_entries=self.ambiguous_entries,
            unmatched_entries=self.unmatched_entries,
        )


class ContextualizedTaxonomyBuilder:
    def __init__(self, taxonomy: EnrichedTaxonomy, context_index: dict[str, ContextIndexEntry]) -> None:
        self.product_accumulators = [_ProductAccumulator(product) for product in taxonomy.products]
        self.product_by_key = {
            self.normalize_name(product_accumulator.product.name): product_accumulator
            for product_accumulator in self.product_accumulators
        }
        self.context_index = context_index

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(name.casefold().split())

    @staticmethod
    def _clean_paths(paths: list[str | None]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for path in paths:
            if path is None:
                continue

            normalized = path.strip()
            if not normalized or normalized in seen:
                continue

            cleaned.append(normalized)
            seen.add(normalized)

        return cleaned

    def build(self) -> ContextualizedTaxonomy:
        stats = _ContextualizationStatsAccumulator(total_context_entries=len(self.context_index))

        for context_entry, entry in self.context_index.items():
            self._attach_best_match(context_entry, entry, stats)

        return ContextualizedTaxonomy(
            products=[product_accumulator.build() for product_accumulator in self.product_accumulators],
            stats=stats.build(),
        )

    def _attach_best_match(
        self,
        context_entry: str,
        entry: ContextIndexEntry,
        stats: _ContextualizationStatsAccumulator,
    ) -> None:
        # The page component is the cleanest anchor. Key files are useful fallback evidence,
        # but broaden the match surface enough that they should not be the first choice.
        page_component_paths = self._clean_paths([entry.page_component])
        page_component_match = self._match_paths(page_component_paths)

        if self._attach_unique_match(
            context_entry,
            entry,
            page_component_match,
            stats=stats,
        ):
            stats.page_component_matches += 1
            return

        page_plus_key_file_paths = self._clean_paths([entry.page_component, *entry.key_files])
        if page_plus_key_file_paths != page_component_paths:
            page_plus_key_file_match = self._match_paths(page_plus_key_file_paths)
            if self._attach_unique_match(
                context_entry,
                entry,
                page_plus_key_file_match,
                stats=stats,
            ):
                stats.page_plus_key_file_matches += 1
                return
            final_match = page_plus_key_file_match
        else:
            final_match = page_component_match

        if final_match.product_keys or final_match.feature_keys:
            stats.ambiguous_entries.append(context_entry)
        else:
            stats.unmatched_entries.append(context_entry)

    def _attach_unique_match(
        self,
        context_entry: str,
        entry: ContextIndexEntry,
        match: _MatchResult,
        stats: _ContextualizationStatsAccumulator,
    ) -> bool:
        if len(match.feature_keys) == 1:
            product_key, feature_key = next(iter(match.feature_keys))
            product_accumulator = self.product_by_key[product_key]
            product_accumulator.context.add_context_entry(
                context_entry,
                entry,
            )
            product_accumulator.feature_by_key[feature_key].context.add_context_entry(
                context_entry,
                entry,
            )
            stats.feature_matches += 1
            return True

        if len(match.product_keys) == 1:
            product_key = next(iter(match.product_keys))
            self.product_by_key[product_key].context.add_context_entry(
                context_entry,
                entry,
            )
            stats.product_matches += 1
            return True

        return False

    def _match_paths(self, candidate_paths: list[str]) -> _MatchResult:
        match = _MatchResult()
        if not candidate_paths:
            return match

        for product_accumulator in self.product_accumulators:
            product_key = self.normalize_name(product_accumulator.product.name)

            if self._matches_any(product_accumulator.product.code_paths, candidate_paths):
                match.product_keys.add(product_key)

            for feature_accumulator in product_accumulator.feature_accumulators:
                if self._matches_any(feature_accumulator.feature.code_paths, candidate_paths):
                    match.feature_keys.add(
                        (
                            product_key,
                            self.normalize_name(feature_accumulator.feature.name),
                        )
                    )

        return match

    @staticmethod
    def _matches_any(patterns: list[str], candidate_paths: list[str]) -> bool:
        return any(
            fnmatch.fnmatch(candidate_path, pattern) for pattern in patterns for candidate_path in candidate_paths
        )


def _load_enriched_taxonomy(domain: str) -> EnrichedTaxonomy:
    enriched_file = _enriched_taxonomy_file(domain)
    if not enriched_file.exists():
        raise RuntimeError(
            f"Missing enriched taxonomy at {enriched_file}. Run `python manage.py enrich_taxonomy {domain}` first."
        )

    return EnrichedTaxonomy.model_validate_json(enriched_file.read_text())


def _load_context_index(domain: str) -> dict[str, ContextIndexEntry]:
    index_file = cache_dir_for_domain(domain) / "_product-context-index.json"
    if not index_file.exists():
        raise RuntimeError(
            f"Missing product context index at {index_file}. Generate `_product-context-index.json` first."
        )

    raw_index = json.loads(index_file.read_text())
    return {context_entry: ContextIndexEntry.model_validate(entry) for context_entry, entry in raw_index.items()}


def contextualize_taxonomy(domain: str, *, force: bool = False, output_fn=None) -> ContextualizedTaxonomy:
    cache_dir = cache_dir_for_domain(domain)
    contextualized_file = cache_dir / "_contextualized_taxonomy.json"

    if contextualized_file.exists() and not force:
        cached = ContextualizedTaxonomy.model_validate_json(contextualized_file.read_text())
        if output_fn:
            output_fn(
                "Using cached contextualized taxonomy: "
                f"{len(cached.products)} products, "
                f"{cached.stats.feature_matches} feature matches, "
                f"{cached.stats.product_matches} product matches"
            )
        return cached

    taxonomy = _load_enriched_taxonomy(domain)
    context_index = _load_context_index(domain)

    if output_fn:
        output_fn(
            f"Contextualizing taxonomy from {len(taxonomy.products)} products "
            f"and {len(context_index)} context-index entries..."
        )

    contextualized = ContextualizedTaxonomyBuilder(taxonomy, context_index).build()
    contextualized_file.write_text(contextualized.model_dump_json(indent=2))

    if output_fn:
        output_fn(
            "Contextualization complete: "
            f"{contextualized.stats.feature_matches} feature matches, "
            f"{contextualized.stats.product_matches} product matches, "
            f"{len(contextualized.stats.ambiguous_entries)} ambiguous, "
            f"{len(contextualized.stats.unmatched_entries)} unmatched"
        )

    return contextualized


def run_contextualize_taxonomy(domain: str, *, force: bool = False, output_fn=None) -> ContextualizedTaxonomy:
    return contextualize_taxonomy(domain, force=force, output_fn=output_fn)
