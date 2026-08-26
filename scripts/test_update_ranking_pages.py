"""Regression tests for numeric-only Zillow ranking updates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from update_ranking_pages import (  # noqa: E402
    CITY_ASSET,
    CITY_PREFIX,
    DEFAULT_TOP_CITY_MAX_SIZE_RANK,
    HUB_PAGE,
    MANIFEST_PATH,
    NEIGHBORHOOD_ASSET,
    NEIGHBORHOOD_PREFIX,
    REGIONAL_PAGES,
    build_update,
    city_signature,
    load_js_asset,
    neighborhood_signature,
    parse_regional_rows,
)


class RankingPageUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs, cls.manifest, cls.report = build_update()

    def test_all_generated_ranking_files_are_current(self) -> None:
        for path, expected in self.outputs.items():
            with self.subTest(path=path.name):
                self.assertTrue(path.exists())
                self.assertEqual(path.read_text(encoding="utf-8-sig"), expected)

    def test_national_membership_and_labels_are_preserved(self) -> None:
        old_city = load_js_asset(CITY_ASSET, CITY_PREFIX)
        new_city_text = self.outputs[CITY_ASSET]
        new_city = __import__("json").loads(new_city_text[len(CITY_PREFIX) :].strip()[:-1])
        self.assertEqual(city_signature(old_city), city_signature(new_city))

        old_neighborhood = load_js_asset(NEIGHBORHOOD_ASSET, NEIGHBORHOOD_PREFIX)
        new_neighborhood_text = self.outputs[NEIGHBORHOOD_ASSET]
        new_neighborhood = __import__("json").loads(
            new_neighborhood_text[len(NEIGHBORHOOD_PREFIX) :].strip()[:-1]
        )
        self.assertEqual(
            neighborhood_signature(old_neighborhood), neighborhood_signature(new_neighborhood)
        )

    def test_regional_membership_is_unchanged_and_complete(self) -> None:
        for page in REGIONAL_PAGES:
            with self.subTest(page=page.name):
                old_text = page.read_text(encoding="utf-8-sig")
                _old_match, old_rows = parse_regional_rows(old_text, page.name)
                _new_match, new_rows = parse_regional_rows(self.outputs[page], page.name)
                self.assertEqual([row["city"] for row in old_rows], [row["city"] for row in new_rows])
                self.assertEqual(len(new_rows), 50)
                self.assertTrue(all(row["typical_price"] is not None for row in new_rows))

    def test_default_top_us_cities_have_current_prices(self) -> None:
        data = load_js_asset(CITY_ASSET, CITY_PREFIX)
        top_rows = [
            row
            for rows in data.values()
            for row in rows
            if int(row["sizeRank"]) <= DEFAULT_TOP_CITY_MAX_SIZE_RANK
        ]
        self.assertGreater(len(top_rows), 100)
        self.assertTrue(all(row["typical_price"] is not None for row in top_rows))

    def test_shared_july_2026_endpoint(self) -> None:
        self.assertEqual(self.manifest["as_of"], "2026-07-31")
        self.assertEqual(self.manifest["sources"]["city_sfr_zhvi"]["latest_date"], "2026-07-31")
        self.assertEqual(
            self.manifest["sources"]["neighborhood_sfr_zhvi"]["latest_date"],
            "2026-07-31",
        )
        self.assertIn(MANIFEST_PATH, self.outputs)
        self.assertIn("Data updated through Jul 31, 2026.", self.outputs[HUB_PAGE])


if __name__ == "__main__":
    unittest.main()
