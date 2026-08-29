"""Regression tests for persistent Matrix data-quality rules."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_matrix_city_mls_data import (  # noqa: E402
    TARGET_SLUGS,
    validate_displayed_series,
)


def load_asset(slug: str) -> dict:
    text = (REPO_ROOT / "assets" / "data" / "mls" / f"{slug}.js").read_text(
        encoding="utf-8"
    )
    marker = "window.SAN_JOSE_MLS_V3_DATA="
    return json.loads(text.split(marker, 1)[1].rstrip(";\n"))


def series_value(payload: dict, metric: str, label: str):
    series = payload["series"][metric]
    return series["values"][series["labels"].index(label)]


class MatrixCityDataTests(unittest.TestCase):
    def test_los_angeles_days_on_market_starts_in_2020_only(self) -> None:
        payload = load_asset("los-angeles")
        self.assertEqual(payload["series"]["salePrice"]["labels"][0], "2016-01")
        self.assertEqual(
            payload["series"]["daysOnMarket"]["labels"][0], "2020-01"
        )
        self.assertEqual(
            payload["metadata"]["seriesStartMonths"],
            {"daysOnMarket": "2020-01"},
        )

    def test_approved_bad_cells_are_gaps(self) -> None:
        expected = {
            "bakersfield": {
                "pricePerSqFt": ["2021-06"],
                "saleToList": ["2021-08"],
            },
            "fresno": {
                "saleToList": ["2018-03", "2018-09", "2023-02"],
            },
            "sacramento": {"pricePerSqFt": ["2020-12"]},
            "stockton": {"pricePerSqFt": ["2025-03"]},
        }
        for slug, metrics in expected.items():
            payload = load_asset(slug)
            for metric, labels in metrics.items():
                for label in labels:
                    with self.subTest(slug=slug, metric=metric, label=label):
                        self.assertIsNone(series_value(payload, metric, label))

    def test_removed_cities_cannot_be_rebuilt_or_reinstalled(self) -> None:
        for slug in ("santa-barbara", "santa-clarita"):
            self.assertNotIn(slug, TARGET_SLUGS)
            self.assertFalse(
                (REPO_ROOT / "assets" / "data" / "mls" / f"{slug}.js").exists()
            )

    def test_future_outlier_gate_flags_obvious_display_errors(self) -> None:
        labels = [f"2026-0{month}" for month in range(1, 6)]
        series = {
            "closedSales": {"labels": labels, "values": [30] * 5},
            "daysOnMarket": {"labels": labels, "values": [20, 21, 0, 22, 23]},
            "pricePerSqFt": {
                "labels": labels,
                "values": [300, 305, 900, 310, 315],
            },
            "saleToList": {
                "labels": labels,
                "values": [100, 101, 125, 100, 99],
            },
        }
        errors = validate_displayed_series("test-city", series)
        self.assertTrue(any("daysOnMarket" in error for error in errors))
        self.assertTrue(any("pricePerSqFt" in error for error in errors))
        self.assertTrue(any("saleToList" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
