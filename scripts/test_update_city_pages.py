"""Regression tests for the generated Zillow sections on all 43 city pages."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from update_city_pages import (  # noqa: E402
    CSS_LINK,
    SHARED_SCRIPT,
    UpdateError,
    build_city_asset,
    copy_digest,
    normalize_page_copy,
    read_json,
    select_neighborhoods,
    transform_page,
    validate_payload,
)


class CityPageUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = read_json(REPO_ROOT / "config" / "city-pages.json")
        cls.payload = read_json(
            REPO_ROOT / "data" / "zillow" / "processed" / "city-pages.json"
        )
        cls.copy_contract = read_json(
            REPO_ROOT / "config" / "city-page-copy-contract.json"
        )
        validate_payload(cls.config, cls.payload)

    def test_all_43_pages_and_assets_are_current(self) -> None:
        pages_with_tables = 0
        pages_without_neighborhood_sections = 0

        for configured_city in self.config["cities"]:
            slug = configured_city["slug"]
            city = self.payload["cities"][slug]
            page_contract = self.copy_contract["cities"][slug]
            selected, missing, _not_added = select_neighborhoods(
                slug, city, self.copy_contract
            )
            page_path = REPO_ROOT / configured_city["page"]
            page = page_path.read_bytes().decode("utf-8")

            with self.subTest(page=configured_city["page"]):
                self.assertEqual(
                    transform_page(
                        page,
                        slug,
                        city,
                        self.payload,
                        page_contract,
                        selected,
                    ),
                    page,
                )
                self.assertEqual(page.count(CSS_LINK), 1)
                expected_canvas_count = (
                    7 if '<section class="sj-mls-dashboard"' in page else 1
                )
                self.assertEqual(
                    len(re.findall(r'<canvas[^>]+id="[^"]+"', page)),
                    expected_canvas_count,
                )
                self.assertEqual(
                    page.count(f'<script src="assets/data/city-pages/{slug}.js"></script>'),
                    1,
                )
                self.assertEqual(page.count(SHARED_SCRIPT), 1)
                self.assertNotRegex(page, r"_zhvi_series\.js")
                self.assertNotRegex(page, r"window\.[A-Z0-9_]+_ZHVI_SERIES")
                self.assertNotIn("<!-- Neighborhood Table Script -->", page)
                self.assertNotIn("<!-- Chart Script -->", page)

                labels = re.findall(r'<div class="stat-label">([^<]+)</div>', page)
                self.assertEqual(
                    labels,
                    [
                        "YoY Price Change",
                        "5-Year Price Change",
                        "10-Year Price Change",
                        "25-Year Price Change",
                        "Median Sale Price",
                        "Median Days on Market",
                    ],
                )
                self.assertEqual(
                    copy_digest(normalize_page_copy(page)),
                    page_contract["page_copy_sha256"],
                )

                if page_contract["neighborhood_section"] and selected:
                    pages_with_tables += 1
                    self.assertEqual(page.count('id="tableBody"'), 1)
                    self.assertNotIn("neighborhood-empty-state", page)
                    self.assertEqual(page.count("NEIGHBORHOOD RANKINGS"), 1)
                else:
                    pages_without_neighborhood_sections += 1
                    self.assertNotIn('id="tableBody"', page)
                    self.assertNotIn("neighborhood-empty-state", page)
                    self.assertNotIn("NEIGHBORHOOD RANKINGS", page)

                asset_path = REPO_ROOT / "assets" / "data" / "city-pages" / f"{slug}.js"
                self.assertEqual(
                    asset_path.read_text(encoding="utf-8"),
                    build_city_asset(slug, city, self.payload, selected),
                )

                if configured_city["page"] == "Santa-Rosa.html":
                    self.assertEqual(missing, ["Santa Rosa Junior College"])
                else:
                    self.assertEqual(missing, [])

        self.assertEqual(pages_with_tables, 34)
        self.assertEqual(pages_without_neighborhood_sections, 9)

    def test_san_jose_approved_copy_is_preserved(self) -> None:
        page = (REPO_ROOT / "San-Jose.html").read_text(encoding="utf-8")
        self.assertIn(
            "Which San Jose neighborhoods have appreciated the most over the last few years? "
            "We cover the top 16 neighborhoods by population over the last 1, 3, 5, 10, "
            "20 and 25 years. All data has been taken from Zillow for single family homes, "
            "and the interactive table allows sorting by any column so you can compare "
            "total return and CAGR side by side across different periods.",
            page,
        )
        self.assertIn(
            "Click any column header to sort &mdash; or visit our "
            '<a href="Appreciation-Rankings-Hub.html">Appreciation Rankings Hub</a> '
            "to explore more regions of California and the US.",
            page,
        )

    def test_routine_refresh_cannot_remove_neighborhood_copy(self) -> None:
        slug = "san-jose"
        configured = next(
            city for city in self.config["cities"] if city["slug"] == slug
        )
        page = (REPO_ROOT / configured["page"]).read_text(encoding="utf-8")
        with self.assertRaisesRegex(
            UpdateError, "routine data refresh may not remove its visible copy"
        ):
            transform_page(
                page,
                slug,
                self.payload["cities"][slug],
                self.payload,
                self.copy_contract["cities"][slug],
                [],
            )

    def test_routine_refresh_rejects_heading_change(self) -> None:
        slug = "san-jose"
        configured = next(
            city for city in self.config["cities"] if city["slug"] == slug
        )
        page = (REPO_ROOT / configured["page"]).read_text(encoding="utf-8")
        altered = page.replace(
            "San Jose Trends from Zillow", "San Jose Real Estate Trends", 1
        )
        selected, _missing, _not_added = select_neighborhoods(
            slug, self.payload["cities"][slug], self.copy_contract
        )
        with self.assertRaisesRegex(UpdateError, "Protected stats copy differs"):
            transform_page(
                altered,
                slug,
                self.payload["cities"][slug],
                self.payload,
                self.copy_contract["cities"][slug],
                selected,
            )

if __name__ == "__main__":
    unittest.main()
