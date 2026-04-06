from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from unittest.mock import patch

from hogli.product.scaffold import _add_to_feature_flags, _render_template
from parameterized import parameterized


class TestRenderTemplate:
    @parameterized.expand(
        [
            ("simple", "my_product", "MyProduct", "MY_PRODUCT", "my-product"),
            ("single_word", "analytics", "Analytics", "ANALYTICS", "analytics"),
            (
                "multi_word",
                "opportunity_solution_trees",
                "OpportunitySolutionTrees",
                "OPPORTUNITY_SOLUTION_TREES",
                "opportunity-solution-trees",
            ),
        ]
    )
    def test_substitutes_all_placeholders(self, _name: str, product: str, pascal: str, upper: str, hyphen: str) -> None:
        template = "name: {product}, class: {Product}, flag: {PRODUCT}, css: {product_hyphen}"
        result = _render_template(template, product)
        assert result == f"name: {product}, class: {pascal}, flag: {upper}, css: {hyphen}"


class TestAddToFeatureFlags:
    CONSTANTS_TEMPLATE = dedent("""\
        export const FEATURE_FLAGS = {
            // Eternal feature flags
            ETERNAL: 'eternal', // owner: #team-a

            // Temporary feature flags
            ALPHA: 'alpha', // owner: #team-a
            ZETA: 'zeta', // owner: #team-z
            // PLEASE KEEP THIS ALPHABETICALLY ORDERED
        } as const
    """)

    def _run(self, tmp_path: Path, product_name: str, content: str | None = None) -> str:
        constants = tmp_path / "constants.tsx"
        constants.write_text(content or self.CONSTANTS_TEMPLATE)
        with patch("hogli.product.scaffold.FEATURE_FLAGS_CONSTANTS", constants):
            _add_to_feature_flags(product_name, dry_run=False)
        return constants.read_text()

    @pytest.mark.parametrize(
        "product, expected_order",
        [
            ("my_product", ["ETERNAL", "ALPHA", "MY_PRODUCT", "ZETA"]),
            ("zzz_product", ["ETERNAL", "ALPHA", "ZETA", "ZZZ_PRODUCT"]),
            ("aaa_product", ["ETERNAL", "AAA_PRODUCT", "ALPHA", "ZETA"]),
        ],
        ids=["middle", "last", "first"],
    )
    def test_inserts_in_alphabetical_order(self, product: str, expected_order: list[str], tmp_path: Path) -> None:
        content = self._run(tmp_path, product)
        lines = content.split("\n")
        key_lines = [
            line.strip().split(":")[0].strip()
            for line in lines
            if line.strip() and not line.strip().startswith("//") and ":" in line and "'" in line
        ]
        assert key_lines == expected_order

    @pytest.mark.parametrize(
        "product, expected_key, expected_value",
        [
            ("my_product", "MY_PRODUCT", "my-product"),
            ("my_cool_product", "MY_COOL_PRODUCT", "my-cool-product"),
            ("analytics", "ANALYTICS", "analytics"),
        ],
        ids=["simple", "multi_word", "single_word"],
    )
    def test_flag_entry_format(self, product: str, expected_key: str, expected_value: str, tmp_path: Path) -> None:
        content = self._run(tmp_path, product)
        assert f"    {expected_key}: '{expected_value}', // owner: #team-CHANGEME" in content

    def test_skips_when_already_present(self, tmp_path: Path) -> None:
        content = self._run(tmp_path, "alpha")
        assert content == self.CONSTANTS_TEMPLATE

    def test_no_op_when_marker_missing(self, tmp_path: Path) -> None:
        original = "export const FEATURE_FLAGS = {} as const\n"
        content = self._run(tmp_path, "my_product", content=original)
        assert content == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        constants = tmp_path / "constants.tsx"
        with patch("hogli.product.scaffold.FEATURE_FLAGS_CONSTANTS", constants):
            _add_to_feature_flags("my_product", dry_run=False)
        assert not constants.exists()
