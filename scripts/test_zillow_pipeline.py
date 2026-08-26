import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zillow_pipeline import (
    REPO_ROOT,
    comparison_date,
    date_columns,
    latest_complete_date,
    parse_number,
    return_metrics,
)


class ZillowPipelineTests(unittest.TestCase):
    def test_city_manifest_has_43_unique_pages_and_region_ids(self):
        manifest = json.loads((REPO_ROOT / "config" / "city-pages.json").read_text(encoding="utf-8"))
        cities = manifest["cities"]
        locations_html = (REPO_ROOT / "locations.html").read_text(encoding="utf-8")
        self.assertEqual(len(cities), 43)
        self.assertEqual(len({city["page"] for city in cities}), 43)
        self.assertEqual(len({city["region_id"] for city in cities}), 43)
        self.assertTrue(all((REPO_ROOT / city["page"]).exists() for city in cities))
        self.assertTrue(all(f'href="{city["page"]}"' in locations_html for city in cities))

    def test_source_manifest_has_all_four_required_datasets(self):
        manifest = json.loads((REPO_ROOT / "config" / "zillow-sources.json").read_text(encoding="utf-8"))
        source_ids = {source["id"] for source in manifest["sources"] if source.get("enabled", True)}
        self.assertEqual(
            source_ids,
            {
                "city_sfr_zhvi",
                "neighborhood_sfr_zhvi",
                "city_sfr_median_sale_price",
                "city_median_days_to_pending",
            },
        )

    def test_date_columns_sorts_and_ignores_metadata(self):
        fields = ["RegionID", "2025-12-31", "RegionName", "2024-12-31"]
        self.assertEqual(date_columns(fields), ["2024-12-31", "2025-12-31"])

    def test_comparison_date_uses_same_month(self):
        dates = ["2024-07-31", "2025-07-31", "2026-07-31"]
        self.assertEqual(comparison_date(dates, "2026-07-31", 1), "2025-07-31")
        self.assertEqual(comparison_date(dates, "2026-07-31", 2), "2024-07-31")

    def test_latest_complete_date_uses_one_shared_city_date(self):
        dates = ["2026-05-31", "2026-06-30", "2026-07-31"]
        rows = [
            {"2026-05-31": "1", "2026-06-30": "2", "2026-07-31": "3"},
            {"2026-05-31": "4", "2026-06-30": "5", "2026-07-31": ""},
        ]
        self.assertEqual(latest_complete_date(dates, rows, "test metric"), "2026-06-30")

    def test_return_and_cagr(self):
        dates = ["2021-07-31", "2025-07-31", "2026-07-31"]
        row = {"2021-07-31": "100", "2025-07-31": "110", "2026-07-31": "121"}
        result = return_metrics(row, dates, "2026-07-31")
        self.assertEqual(result["1y"]["total_return_pct"], 10.0)
        self.assertEqual(result["1y"]["cagr_pct"], 10.0)
        self.assertEqual(result["5y"]["total_return_pct"], 21.0)
        self.assertAlmostEqual(result["5y"]["cagr_pct"], 3.886, places=3)

    def test_missing_history_produces_null_metrics(self):
        dates = ["2025-07-31", "2026-07-31"]
        row = {"2025-07-31": "", "2026-07-31": "500000"}
        result = return_metrics(row, dates, "2026-07-31")
        self.assertIsNone(result["1y"]["total_return_pct"])
        self.assertIsNone(result["1y"]["cagr_pct"])

    def test_parse_number_handles_blanks(self):
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number(None))
        self.assertEqual(parse_number("123.45"), 123.45)


if __name__ == "__main__":
    unittest.main()
