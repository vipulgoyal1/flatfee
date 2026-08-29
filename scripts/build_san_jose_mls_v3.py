#!/usr/bin/env python3
"""Build the raw monthly data asset for the San Jose MLS charts v3 sample.

Version 3 intentionally performs no seasonal adjustment and no moving average.
The browser groups the reported monthly values into yearly, quarterly, or
monthly views. Closed-sales counts are summed; the other reported monthly
metrics are averaged when a quarter or year is selected.

Run from the website repository:
    python scripts/build_san_jose_mls_v3.py

Override the local data folder if needed:
    python scripts/build_san_jose_mls_v3.py --mls-root "D:\\MLS Data"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


DEFAULT_MLS_ROOT = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
)
DEFAULT_OUTPUT = Path("assets/data/mls/san-jose-v3.js")
MONTH_INDEX = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

SERIES_CONFIG = {
    "salePrice": {
        "file": "Sale Price, Median.csv",
        "decimals": 0,
        "aggregation": "mean",
        "anomalies": set(),
    },
    "daysOnMarket": {
        "file": "Days to Sell, Median.csv",
        "decimals": 1,
        "aggregation": "mean",
        "anomalies": {"2020-05"},
    },
    "saleToList": {
        "file": "Sale Price to List Price Ratio.csv",
        "decimals": 2,
        "aggregation": "mean",
        "anomalies": {"2021-03", "2023-12"},
    },
    "closedSales": {
        "file": "Sales, Number of.csv",
        "decimals": 0,
        "aggregation": "sum",
        "anomalies": set(),
    },
    "pricePerSqFt": {
        "file": "PriceSqFt Ratio.csv",
        "decimals": 1,
        "aggregation": "mean",
        "anomalies": set(),
    },
}


def parse_numeric(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned:
        return None
    return float(cleaned)


def rounded(value: float | None, decimals: int) -> float | int | None:
    if value is None:
        return None
    if decimals == 0:
        return int(round(value))
    return round(value, decimals)


def read_wide_monthly_csv(path: Path, config: dict) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required MLS file is missing: {path}")

    by_date: dict[str, float | None] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or reader.fieldnames[0] != "Month":
            raise ValueError(f"Unexpected CSV layout in {path}")

        year_columns: list[tuple[str, int]] = []
        for column in reader.fieldnames[1:]:
            match = re.search(r"(20\d{2})$", column)
            if match:
                year_columns.append((column, int(match.group(1))))
        if not year_columns:
            raise ValueError(f"No year columns found in {path}")

        for row in reader:
            month_name = (row.get("Month") or "").strip()
            if month_name not in MONTH_INDEX:
                continue
            month = MONTH_INDEX[month_name]
            for column, year in year_columns:
                label = f"{year:04d}-{month:02d}"
                value = parse_numeric(row.get(column) or "")
                if value is not None:
                    by_date[label] = None if label in config["anomalies"] else value

    labels = sorted(by_date)
    if len(labels) < 60:
        raise ValueError(f"At least five years of monthly data are required: {path}")
    return {
        "labels": labels,
        "values": [rounded(by_date[label], config["decimals"]) for label in labels],
        "aggregation": config["aggregation"],
    }


def common_latest_label(series: dict[str, dict]) -> str:
    latest = {name: values["labels"][-1] for name, values in series.items()}
    if len(set(latest.values())) != 1:
        raise ValueError(f"Monthly MLS files do not end in the same month: {latest}")
    return next(iter(latest.values()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mls-root",
        type=Path,
        default=Path(os.environ.get("FFR_MLS_DATA_ROOT", DEFAULT_MLS_ROOT)),
        help="Local MLS Data folder",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JavaScript data asset to write",
    )
    args = parser.parse_args()

    city_folder = args.mls_root / "Cities" / "San Jose"
    series = {
        name: read_wide_monthly_csv(city_folder / config["file"], config)
        for name, config in SERIES_CONFIG.items()
    }
    latest_label = common_latest_label(series)

    payload = {
        "metadata": {
            "city": "San Jose",
            "propertyType": "Single-family homes",
            "firstMonth": min(values["labels"][0] for values in series.values()),
            "latestMonth": latest_label,
            "method": (
                "No seasonal adjustment and no moving average. Quarterly and "
                "yearly views sum closed sales and take the arithmetic mean of "
                "the reported monthly values for all other metrics."
            ),
            "anomaliesExcluded": {
                "daysOnMarket": ["2020-05"],
                "saleToList": ["2021-03", "2023-12"],
            },
        },
        "series": series,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    args.output.write_text(
        "/* Generated by scripts/build_san_jose_mls_v3.py. */\n"
        f"window.SAN_JOSE_MLS_V3_DATA={json_payload};\n",
        encoding="utf-8",
    )

    print(f"Wrote {args.output}")
    print(f"Monthly coverage: {payload['metadata']['firstMonth']} through {latest_label}")


if __name__ == "__main__":
    main()
