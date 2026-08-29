#!/usr/bin/env python3
"""Build the static data asset for the San Jose MLS charts v2 sample.

The script uses only Python's standard library. It reads the locally stored,
wide-format MLS CSV files, removes three documented source anomalies, estimates
month-of-year seasonal factors, and writes a browser-ready JavaScript asset.

Seasonal adjustment method:
1. Estimate the underlying level with a centered 12-month moving average.
2. Calculate each month's typical ratio to (or difference from) that level.
3. Use the median across years to reduce sensitivity to one-off market shocks.
4. Normalize the 12 monthly factors and remove them from the raw series.
5. Calculate the displayed trend as a trailing 3-month average of the adjusted
   series.

Run from the website repository:
    python scripts/build_san_jose_mls_v2.py

Override the local data folder if needed:
    python scripts/build_san_jose_mls_v2.py --mls-root "D:\\MLS Data"
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
from pathlib import Path
from typing import Iterable


DEFAULT_MLS_ROOT = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
)
DEFAULT_OUTPUT = Path("assets/data/mls/san-jose-v2.js")
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
        "adjustment": "multiplicative",
        "decimals": 0,
        "anomalies": set(),
    },
    "daysOnMarket": {
        "file": "Days to Sell, Median.csv",
        "adjustment": "additive",
        "decimals": 1,
        "anomalies": {"2020-05"},
    },
    "saleToList": {
        "file": "Sale Price to List Price Ratio.csv",
        "adjustment": "additive",
        "decimals": 2,
        "anomalies": {"2021-03", "2023-12"},
    },
    "closedSales": {
        "file": "Sales, Number of.csv",
        "adjustment": "multiplicative",
        "decimals": 1,
        "anomalies": set(),
    },
    "pricePerSqFt": {
        "file": "PriceSqFt Ratio.csv",
        "adjustment": "multiplicative",
        "decimals": 1,
        "anomalies": set(),
    },
}


def parse_numeric(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned:
        return None
    return float(cleaned)


def read_wide_monthly_csv(path: Path, anomalies: set[str]) -> tuple[list[str], list[float | None]]:
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
                    by_date[label] = None if label in anomalies else value

    labels = sorted(by_date)
    values = [by_date[label] for label in labels]
    if len(labels) < 60:
        raise ValueError(f"At least five years of monthly data are required: {path}")
    return labels, values


def interpolate(values: list[float | None]) -> list[float]:
    result: list[float] = []
    known = [index for index, value in enumerate(values) if value is not None]
    if not known:
        raise ValueError("Series contains no usable observations")

    for index, value in enumerate(values):
        if value is not None:
            result.append(float(value))
            continue
        before = next((item for item in reversed(known) if item < index), None)
        after = next((item for item in known if item > index), None)
        if before is None:
            result.append(float(values[after]))  # type: ignore[arg-type]
        elif after is None:
            result.append(float(values[before]))  # type: ignore[arg-type]
        else:
            fraction = (index - before) / (after - before)
            start = float(values[before])  # type: ignore[arg-type]
            end = float(values[after])  # type: ignore[arg-type]
            result.append(start + (end - start) * fraction)
    return result


def centered_twelve_month_average(values: list[float]) -> list[float | None]:
    """Return the classical centered 2x12 moving average."""
    trend: list[float | None] = [None] * len(values)
    for index in range(6, len(values) - 6):
        weighted_sum = 0.5 * values[index - 6] + 0.5 * values[index + 6]
        weighted_sum += sum(values[index - 5 : index + 6])
        trend[index] = weighted_sum / 12.0
    return trend


def normalized_factors(
    values: list[float],
    trend: list[float | None],
    adjustment: str,
) -> list[float]:
    candidates: list[list[float]] = [[] for _ in range(12)]
    for index, (value, level) in enumerate(zip(values, trend)):
        if level is None:
            continue
        if adjustment == "multiplicative":
            if level > 0:
                candidates[index % 12].append(value / level)
        else:
            candidates[index % 12].append(value - level)

    factors = []
    for month_values in candidates:
        if len(month_values) < 3:
            raise ValueError("Insufficient history to estimate all 12 seasonal factors")
        factors.append(statistics.median(month_values))

    if adjustment == "multiplicative":
        average = sum(factors) / 12.0
        return [factor / average for factor in factors]
    average = sum(factors) / 12.0
    return [factor - average for factor in factors]


def trailing_average(values: list[float], months: int = 3) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index < months - 1:
            result.append(None)
        else:
            result.append(sum(values[index - months + 1 : index + 1]) / months)
    return result


def rounded(values: Iterable[float | None], decimals: int) -> list[float | int | None]:
    output: list[float | int | None] = []
    for value in values:
        if value is None:
            output.append(None)
        elif decimals == 0:
            output.append(int(round(value)))
        else:
            output.append(round(value, decimals))
    return output


def build_series(path: Path, config: dict) -> dict:
    labels, raw = read_wide_monthly_csv(path, config["anomalies"])
    working = interpolate(raw)
    centered = centered_twelve_month_average(working)
    factors = normalized_factors(working, centered, config["adjustment"])

    if config["adjustment"] == "multiplicative":
        adjusted_model = [
            value / factors[index % 12] for index, value in enumerate(working)
        ]
    else:
        adjusted_model = [
            value - factors[index % 12] for index, value in enumerate(working)
        ]

    adjusted = [
        adjusted_model[index] if raw_value is not None else None
        for index, raw_value in enumerate(raw)
    ]
    trend = trailing_average(adjusted_model, 3)
    decimals = config["decimals"]
    return {
        "labels": labels,
        "raw": rounded(raw, decimals),
        "adjusted": rounded(adjusted, decimals),
        "trend": rounded(trend, decimals),
        "seasonalFactors": rounded(factors, 4),
    }


def read_new_listings(path: Path, limit: int = 12) -> list[dict[str, int | str]]:
    if not path.exists():
        raise FileNotFoundError(f"New-listings comparison file is missing: {path}")
    rows: list[dict[str, int | str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            city = (row.get("City") or "").strip()
            value = parse_numeric(row.get("New Listings, Number of") or "")
            if city and value is not None:
                rows.append({"city": city, "value": int(round(value))})
    rows.sort(key=lambda item: int(item["value"]), reverse=True)
    return rows[:limit]


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
        name: build_series(city_folder / config["file"], config)
        for name, config in SERIES_CONFIG.items()
    }
    latest_label = common_latest_label(series)
    new_listings = read_new_listings(
        args.mls_root / "Other" / "City wise" / "New Listings, Number of - 5yrs.csv"
    )

    payload = {
        "metadata": {
            "city": "San Jose",
            "propertyType": "Single-family homes",
            "firstMonth": min(values["labels"][0] for values in series.values()),
            "latestMonth": latest_label,
            "method": (
                "Median month-of-year factors calculated against a centered "
                "12-month moving average; displayed trend is a trailing "
                "3-month average of seasonally adjusted values."
            ),
            "anomaliesExcluded": {
                "daysOnMarket": ["2020-05"],
                "saleToList": ["2021-03", "2023-12"],
            },
            "newListingsCoverage": (
                "Stored file contains cumulative five-year city totals, not a "
                "monthly San Jose series."
            ),
        },
        "series": series,
        "newListings": new_listings,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    args.output.write_text(
        "/* Generated by scripts/build_san_jose_mls_v2.py. */\n"
        f"window.SAN_JOSE_MLS_V2_DATA={json_payload};\n",
        encoding="utf-8",
    )

    print(f"Wrote {args.output}")
    print(f"Monthly coverage: {payload['metadata']['firstMonth']} through {latest_label}")
    print(f"New-listings comparison cities: {len(new_listings)}")


if __name__ == "__main__":
    main()
