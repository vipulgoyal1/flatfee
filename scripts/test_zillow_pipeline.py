import json
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zillow_pipeline import (
    REPO_ROOT,
    comparison_date,
    date_columns,
    latest_complete_date,
    parse_number,
    return_metrics,
    retained_market_metric,
    read_city_rows,
    PipelineError,
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

    def retained_fixture(self):
        city = {"slug": "milpitas", "name": "Milpitas", "region_id": 39798,
                "county": "Santa Clara County", "page": "Milpitas.html",
                "retain_missing_metrics": ["median_sale_price"]}
        metric = {"as_of": "2026-06-30", "value": 1307366.0,
                  "display_value": 1307366, "unit": "USD",
                  "series": {"dates": ["2026-06-30"], "values": [1307366.0]}}
        previous = {"cities": {"milpitas": {**city, "market_snapshot": {
            "median_sale_price": metric}}}}
        return city, previous, metric

    def test_approved_retention_keeps_value_date_and_does_not_mutate_previous(self):
        city, previous, original = self.retained_fixture()
        retained = retained_market_metric(previous, city, "median_sale_price", "2026-07-31")
        self.assertEqual(retained["value"], 1307366.0)
        self.assertEqual(retained["as_of"], "2026-06-30")
        self.assertEqual(retained["source_latest_date"], "2026-07-31")
        self.assertTrue(retained["retained_from_previous"])
        self.assertNotIn("retained_from_previous", original)
        # Repeated builds must keep the same dated source, not move its date forward.
        previous["cities"]["milpitas"]["market_snapshot"]["median_sale_price"] = retained
        self.assertEqual(retained_market_metric(previous, city, "median_sale_price", "2026-08-31")["as_of"], "2026-06-30")

    def test_retention_requires_approval_identity_and_valid_prior_series(self):
        city, previous, metric = self.retained_fixture()
        for changed in ({**city, "retain_missing_metrics": []}, {**city, "region_id": 123}):
            with self.assertRaises(PipelineError):
                retained_market_metric(previous, changed, "median_sale_price", "2026-07-31")
        metric["series"]["values"] = [1]
        with self.assertRaises(PipelineError):
            retained_market_metric(previous, city, "median_sale_price", "2026-07-31")

    def test_missing_city_exception_does_not_hold_back_other_city_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text("RegionID,2026-06-30,2026-07-31\n123,100,200\n", encoding="utf-8")
            dates, rows = read_city_rows(path, {123, 39798}, {39798})
            self.assertEqual(latest_complete_date(dates, rows.values(), "sale price"), "2026-07-31")
            with self.assertRaises(PipelineError):
                read_city_rows(path, {123, 39798, 456}, {39798})
            with self.assertRaises(PipelineError):
                read_city_rows(path, {123, 39798})


if __name__ == "__main__":
    unittest.main()
