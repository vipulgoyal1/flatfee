#!/usr/bin/env python3
"""Validate and build raw monthly MLS chart assets for configured cities.

The source files are the local wide-format CSVs downloaded from Aculist. The
generated browser assets contain no seasonal adjustment or moving average.
Obvious source errors are converted to null only when listed in
``KNOWN_ANOMALIES`` below; every other structural or range error stops the run.

Examples:
    python scripts/build_city_mls_data.py --check
    python scripts/build_city_mls_data.py --write
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MLS_ROOT = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
    r"\Aculist Downloads\2026-08-28"
)
CONFIG_PATH = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "assets" / "data" / "mls"

MONTH_INDEX = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

SERIES_CONFIG = {
    "salePrice": {
        "file": "Sale Price, Median.csv", "decimals": 0,
        "aggregation": "mean", "minimum": 50_000, "maximum": 10_000_000,
    },
    "daysOnMarket": {
        "file": "Days to Sell, Median.csv", "decimals": 1,
        "aggregation": "mean", "minimum": 1, "maximum": 365,
    },
    "saleToList": {
        "file": "Sale Price to List Price Ratio.csv", "decimals": 2,
        "aggregation": "mean", "minimum": 70, "maximum": 200,
    },
    "closedSales": {
        "file": "Sales, Number of.csv", "decimals": 0,
        "aggregation": "sum", "minimum": 0, "maximum": 20_000,
    },
    "pricePerSqFt": {
        "file": "PriceSqFt Ratio.csv", "decimals": 1,
        "aggregation": "mean", "minimum": 25, "maximum": 5_000,
    },
}

# These are visibly invalid values in Aculist's average-price-per-square-foot
# field, not market moves. They remain null; no replacement is invented.
KNOWN_ANOMALIES = {
    "berkeley": {"pricePerSqFt": {"2019-07"}},
    "oakland": {"pricePerSqFt": {"2018-07", "2018-08", "2019-02"}},
    "san-francisco": {"pricePerSqFt": {"2017-05"}},
}

FOLDER_ALIASES = {
    "anaheim": "Anheim",
    "santa-clarita": "Santa Claritta",
}


def parse_numeric(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    return None if not cleaned else float(cleaned)


def rounded(value: float | None, decimals: int) -> float | int | None:
    if value is None:
        return None
    if decimals == 0:
        return int(round(value))
    return round(value, decimals)


def configured_cities() -> list[dict]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return config["cities"]


def city_folder(mls_root: Path, city: dict) -> Path:
    direct_folder = mls_root / city["name"]
    if direct_folder.is_dir():
        return direct_folder
    folder_name = FOLDER_ALIASES.get(city["slug"], city["name"])
    return mls_root / "Cities" / folder_name


def read_series(path: Path, city_slug: str, metric: str, config: dict) -> tuple[dict, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required MLS file is missing: {path}")

    by_date: dict[str, float | None] = {}
    errors: list[str] = []
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
                    if label in KNOWN_ANOMALIES.get(city_slug, {}).get(metric, set()):
                        by_date[label] = None
                    else:
                        if value < config["minimum"] or value > config["maximum"]:
                            errors.append(
                                f"{city_slug}: {metric} {label}={value:g} is outside "
                                f"{config['minimum']:g}..{config['maximum']:g}"
                            )
                        by_date[label] = value

    labels = sorted(by_date)
    if len(labels) < 60:
        errors.append(f"{city_slug}: {metric} has only {len(labels)} populated months")
    return {
        "labels": labels,
        "values": [rounded(by_date[label], config["decimals"]) for label in labels],
        "aggregation": config["aggregation"],
    }, errors


def build_city_payload(mls_root: Path, city: dict) -> tuple[dict, list[str]]:
    folder = city_folder(mls_root, city)
    if not folder.is_dir():
        raise FileNotFoundError(f"MLS city folder is missing: {folder}")

    series: dict[str, dict] = {}
    errors: list[str] = []
    for metric, config in SERIES_CONFIG.items():
        values, metric_errors = read_series(
            folder / config["file"], city["slug"], metric, config
        )
        series[metric] = values
        errors.extend(metric_errors)

    first_labels = {metric: values["labels"][0] for metric, values in series.items()}
    latest_labels = {metric: values["labels"][-1] for metric, values in series.items()}
    if len(set(first_labels.values())) != 1:
        errors.append(f"{city['slug']}: first months differ: {first_labels}")
    if len(set(latest_labels.values())) != 1:
        errors.append(f"{city['slug']}: latest months differ: {latest_labels}")

    common_labels = next(iter(series.values()))["labels"]
    for metric, values in series.items():
        if values["labels"] != common_labels:
            errors.append(f"{city['slug']}: {metric} month coverage does not align")

    anomalies = {
        metric: sorted(labels)
        for metric, labels in KNOWN_ANOMALIES.get(city["slug"], {}).items()
    }
    payload = {
        "metadata": {
            "city": city["name"],
            "propertyType": "Single-family homes",
            "firstMonth": min(first_labels.values()),
            "latestMonth": min(latest_labels.values()),
            "method": (
                "No seasonal adjustment and no moving average. Quarterly and "
                "yearly views sum closed sales and take the arithmetic mean of "
                "the reported monthly values for all other metrics."
            ),
            "anomaliesExcluded": anomalies,
        },
        "series": series,
    }
    return payload, errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate without writing (default)")
    mode.add_argument("--write", action="store_true", help="Validate, then write all assets")
    parser.add_argument(
        "--mls-root", type=Path,
        default=Path(os.environ.get("FFR_MLS_DATA_ROOT", DEFAULT_MLS_ROOT)),
        help="Local MLS Data folder",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--summary", type=Path,
        help=(
            "Aculist download-summary.json. When supplied, build only cities "
            "with at least --minimum-months observations."
        ),
    )
    parser.add_argument("--minimum-months", type=int, default=120)
    args = parser.parse_args()

    built: list[tuple[dict, dict]] = []
    all_errors: list[str] = []
    cities = configured_cities()
    if args.summary:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        eligible_names = {
            item["city"] for item in summary["available"]
            if item["single_family_months"] >= args.minimum_months
        }
        cities = [city for city in cities if city["name"] in eligible_names]

    for city in cities:
        try:
            payload, errors = build_city_payload(args.mls_root, city)
            built.append((city, payload))
            all_errors.extend(errors)
        except (FileNotFoundError, ValueError) as exc:
            all_errors.append(str(exc))

    if all_errors:
        print("VALIDATION FAILED")
        for error in all_errors:
            print(f"- {error}")
        raise SystemExit(1)

    coverage: dict[tuple[str, str], list[str]] = {}
    for city, payload in built:
        key = (payload["metadata"]["firstMonth"], payload["metadata"]["latestMonth"])
        coverage.setdefault(key, []).append(city["name"])

    print(f"Validated {len(built)} cities and {len(SERIES_CONFIG)} metrics per city.")
    for (first_month, latest_month), names in sorted(coverage.items()):
        print(f"Coverage {first_month} through {latest_month}: {len(names)} cities")
        if len(coverage) > 1:
            print("  " + ", ".join(names))

    if args.write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for city, payload in built:
            output = args.output_dir / f"{city['slug']}.js"
            json_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            output.write_text(
                "/* Generated by scripts/build_city_mls_data.py. */\n"
                f"window.SAN_JOSE_MLS_V3_DATA={json_payload};\n",
                encoding="utf-8",
            )
        print(f"Wrote {len(built)} assets to {args.output_dir}")


if __name__ == "__main__":
    main()
