from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from update_cma_data import (  # noqa: E402
    CmaDataError,
    JS_PREFIX,
    build_payload,
    parse_javascript,
    render_cma_html,
    render_javascript,
    validate_payload,
)


class UpdateCmaDataTests(unittest.TestCase):
    def write_source(self, rows: list[dict[str, str]], dates: list[str]) -> Path:
        temporary = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", suffix=".csv", delete=False
        )
        path = Path(temporary.name)
        with temporary:
            fields = [
                "RegionID",
                "SizeRank",
                "RegionName",
                "RegionType",
                "StateName",
                "State",
                "Metro",
                "CountyName",
                *dates,
            ]
            writer = csv.DictWriter(temporary, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_builds_all_california_cities_and_excludes_other_states(self) -> None:
        source = self.write_source(
            [
                {
                    "RegionID": "2",
                    "SizeRank": "20",
                    "RegionName": "Beta",
                    "State": "CA",
                    "Metro": "Beta Metro",
                    "CountyName": "Beta County",
                    "2026-02-28": "220.125",
                    "2026-01-31": "200",
                },
                {
                    "RegionID": "1",
                    "SizeRank": "10",
                    "RegionName": "Alpha",
                    "State": "CA",
                    "Metro": "",
                    "CountyName": "Alpha County",
                    "2026-02-28": "110",
                    "2026-01-31": "",
                },
                {
                    "RegionID": "3",
                    "SizeRank": "1",
                    "RegionName": "Elsewhere",
                    "State": "NV",
                    "Metro": "Elsewhere Metro",
                    "CountyName": "Elsewhere County",
                    "2026-02-28": "999",
                    "2026-01-31": "900",
                },
            ],
            ["2026-02-28", "2026-01-31"],
        )

        payload = build_payload(source, minimum_cities=2)

        self.assertEqual(payload["dates"], ["2026-01-31", "2026-02-28"])
        self.assertEqual([city["name"] for city in payload["cities"]], ["Alpha", "Beta"])
        self.assertEqual(payload["cities"][0]["values"], [None, 110.0])
        self.assertEqual(payload["cities"][1]["values"], [200.0, 220.12])

    def test_javascript_round_trip_preserves_expected_schema(self) -> None:
        payload = {
            "dates": ["2026-07-31"],
            "cities": [
                {
                    "id": "1",
                    "rank": 1,
                    "name": "Example",
                    "county": "Example County",
                    "metro": "Example Metro",
                    "values": [123.45],
                }
            ],
        }
        validate_payload(payload, minimum_cities=1)
        rendered = render_javascript(payload)

        self.assertTrue(rendered.startswith(JS_PREFIX))
        self.assertEqual(parse_javascript(rendered), payload)
        json.loads(rendered[len(JS_PREFIX) : -2])

    def test_rejects_duplicate_city_ids(self) -> None:
        city = {
            "id": "1",
            "rank": 1,
            "name": "Example",
            "county": "Example County",
            "metro": "",
            "values": [100.0],
        }
        with self.assertRaisesRegex(CmaDataError, "Duplicate California RegionID"):
            validate_payload(
                {"dates": ["2026-07-31"], "cities": [city, dict(city)]},
                minimum_cities=2,
            )

    def test_updates_only_the_cma_dataset_month_fields(self) -> None:
        original = (
            '<p>Keep this copy.</p>\n'
            '<span class="metric-label">Dec 2025 Adjusted $/sf</span>\n'
            '<span class="metric-label">Dec 2025 Adjusted Range</span>\n'
            '<script src="assets/data/ca_cities_zhvi_data.js?v=202512"></script>\n'
        )
        expected = (
            '<p>Keep this copy.</p>\n'
            '<span class="metric-label">Jul 2026 Adjusted $/sf</span>\n'
            '<span class="metric-label">Jul 2026 Adjusted Range</span>\n'
            '<script src="assets/data/ca_cities_zhvi_data.js?v=202607"></script>\n'
        )

        self.assertEqual(render_cma_html(original, "2026-07-31"), expected)


if __name__ == "__main__":
    unittest.main()
