#!/usr/bin/env python3
"""Download clean MLSListings/Aculist monthly data for configured city pages.

The endpoint and query shape are taken from the signed-in MLSListings
``Reports & Statistics`` page. The script intentionally writes to a dated
download folder and never overwrites the existing ``MLS Data/Cities`` files.

The source API dates each published month on the first day of the following
month. Aculist's own CSV export renders that UTC timestamp in Pacific time, so
``2026-08-01T00:00:00Z`` is the July 2026 observation. ``display_month`` below
reproduces that convention by subtracting one day.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_MLS_ROOT = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
)
DEFAULT_OUTPUT = DEFAULT_MLS_ROOT / "Aculist Downloads" / "2026-08-28"

API_URL = (
    "https://aculist-widget-api-cdn.mlslmedia.com/"
    "Growth/MarketTrendsYTDExpanded_KPI"
)
SOURCE_CLASS = "Residential - Single Family"
FIRST_SOURCE_YEAR = 2016

METRICS = {
    "Sale Price, Median.csv": {
        "field": "MedSalePrice",
        "header": "Sale Price, Median",
        "format": lambda value: f"${int(round(value)):,}",
    },
    "Days to Sell, Median.csv": {
        "field": "SoldMedDOM",
        "header": "Days to Sell, Median",
        "format": lambda value: str(int(round(value))),
    },
    "Sale Price to List Price Ratio.csv": {
        "field": "AvgSaleOverListPrice",
        "header": "Sale Price to List Price Ratio",
        "format": lambda value: f"{value * 100:.1f}%",
    },
    "Sales, Number of.csv": {
        "field": "SoldCount",
        "header": "Sales, Number of",
        "format": lambda value: str(int(round(value))),
    },
    "PriceSqFt Ratio.csv": {
        "field": "AvgSalePricePerSqft",
        "header": "Price/SqFt Ratio",
        "format": lambda value: f"${int(round(value)):,}",
    },
}

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def configured_cities() -> list[dict]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return payload["cities"]


def api_uri(city_name: str) -> str:
    escaped_name = city_name.replace("'", "''")
    filter_value = (
        "((Class eq 'Residential - Single Family' or "
        "Class eq 'Residential - Common Interest') and "
        "PeriodType eq 'Month' and "
        f"(Year gt {FIRST_SOURCE_YEAR - 1}) and "
        "((GeographyType eq 'City' and "
        f"GeographyName eq '{escaped_name}')))"
    )
    query = urllib.parse.urlencode(
        {"$filter": filter_value, "$orderby": "PeriodValue desc"}
    )
    return f"{API_URL}?{query}"


def download_city(city_name: str) -> tuple[str, list[dict]]:
    uri = api_uri(city_name)
    request = urllib.request.Request(
        uri,
        headers={
            "Accept": "application/json",
            "User-Agent": "FlatFee-MLS-Updater/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.load(response)
    return uri, payload.get("value", [])


def display_month(row: dict) -> str:
    source_date = datetime.fromisoformat(row["DateValue"].replace("Z", "+00:00"))
    displayed_date = source_date.astimezone(timezone.utc) - timedelta(days=1)
    return displayed_date.strftime("%Y-%m")


def single_family_rows(rows: list[dict], expected_county: str) -> list[dict]:
    county_name = expected_county.removesuffix(" County")
    selected = [
        row for row in rows
        if row.get("Class") == SOURCE_CLASS
        and (row.get("CountyName") or row.get("County")) == county_name
    ]
    selected.sort(key=lambda row: row["PeriodValue"])
    return selected


def write_long_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "display_month", "source_period", "source_date", "city", "county",
        "median_sale_price", "median_days_on_market", "sale_to_list_ratio",
        "closed_sales", "average_price_per_sqft",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "display_month": display_month(row),
                    "source_period": row["Period"],
                    "source_date": row["DateValue"],
                    "city": row["GeographyName"],
                    "county": row.get("CountyName") or row.get("County"),
                    "median_sale_price": row.get("MedSalePrice"),
                    "median_days_on_market": row.get("SoldMedDOM"),
                    "sale_to_list_ratio": row.get("AvgSaleOverListPrice"),
                    "closed_sales": row.get("SoldCount"),
                    "average_price_per_sqft": row.get("AvgSalePricePerSqft"),
                }
            )


def write_wide_csv(path: Path, rows: list[dict], metric: dict) -> None:
    by_month: dict[int, dict[int, object]] = defaultdict(dict)
    years: set[int] = set()
    for row in rows:
        label = display_month(row)
        year, month = map(int, label.split("-"))
        if year < FIRST_SOURCE_YEAR:
            continue
        years.add(year)
        by_month[month][year] = row.get(metric["field"])

    ordered_years = sorted(years)
    header = ["Month"] + [f"{metric['header']} {year}" for year in ordered_years]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for month_index, month_name in enumerate(MONTH_NAMES, start=1):
            output_row = [month_name]
            for year in ordered_years:
                value = by_month.get(month_index, {}).get(year)
                output_row.append("" if value is None else metric["format"](value))
            writer.writerow(output_row)


def validate_rows(city_name: str, rows: list[dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_periods: set[str] = set()
    for row in rows:
        period = row.get("Period")
        if period in seen_periods:
            errors.append(f"duplicate source period {period}")
        seen_periods.add(period)
        for metric in METRICS.values():
            value = row.get(metric["field"])
            if value is None:
                errors.append(f"{period}: missing {metric['field']}")
        price_per_sqft = row.get("AvgSalePricePerSqft")
        if price_per_sqft is not None and not 25 <= price_per_sqft <= 5000:
            warnings.append(
                f"{period}: suspicious AvgSalePricePerSqft {price_per_sqft}"
            )
        sale_to_list = row.get("AvgSaleOverListPrice")
        if sale_to_list is not None and not 0.5 <= sale_to_list <= 2:
            warnings.append(
                f"{period}: suspicious AvgSaleOverListPrice {sale_to_list}"
            )
    if rows and len(rows) < 100:
        warnings.append(f"only {len(rows)} monthly single-family rows")
    return (
        [f"{city_name}: {error}" for error in errors],
        [f"{city_name}: {warning}" for warning in warnings],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(os.environ.get("FFR_ACULIST_OUTPUT", DEFAULT_OUTPUT)),
    )
    parser.add_argument("--delay", type=float, default=0.12)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    available: list[dict] = []
    unavailable: list[str] = []
    validation_errors: list[str] = []
    validation_warnings: list[str] = []

    for index, city in enumerate(configured_cities(), start=1):
        uri, rows = download_city(city["name"])
        if not rows:
            unavailable.append(city["name"])
            print(f"[{index:02d}/43] unavailable: {city['name']}")
            time.sleep(args.delay)
            continue

        sfr_rows = single_family_rows(rows, city["county"])
        city_errors, city_warnings = validate_rows(city["name"], sfr_rows)
        validation_errors.extend(city_errors)
        validation_warnings.extend(city_warnings)
        city_dir = args.output / city["name"]
        city_dir.mkdir(parents=True, exist_ok=True)
        (city_dir / "raw-api.json").write_text(
            json.dumps(
                {"source_url": uri, "downloaded_rows": len(rows), "value": rows},
                indent=2,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )
        write_long_csv(city_dir / "Single-Family-Monthly.csv", sfr_rows)
        for filename, metric in METRICS.items():
            write_wide_csv(city_dir / filename, sfr_rows, metric)

        first_display = display_month(sfr_rows[0])
        latest_display = display_month(sfr_rows[-1])
        available.append(
            {
                "city": city["name"],
                "slug": city["slug"],
                "api_rows": len(rows),
                "single_family_months": len(sfr_rows),
                "first_display_month": first_display,
                "latest_display_month": latest_display,
                "first_source_period": sfr_rows[0]["Period"],
                "latest_source_period": sfr_rows[-1]["Period"],
            }
        )
        print(
            f"[{index:02d}/43] downloaded: {city['name']} "
            f"({first_display} through {latest_display})"
        )
        time.sleep(args.delay)

    summary = {
        "source": "MLSListings Reports & Statistics / Aculist",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "api": API_URL,
        "property_type": SOURCE_CLASS,
        "date_note": (
            "Display month is DateValue minus one day, matching Aculist's own "
            "CSV export in Pacific time."
        ),
        "available_count": len(available),
        "available": available,
        "unavailable_count": len(unavailable),
        "unavailable": unavailable,
        "validation_warnings": validation_warnings,
        "validation_errors": validation_errors,
    }
    (args.output / "download-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nDownloaded {len(available)} cities; unavailable: {len(unavailable)}")
    print(f"Output: {args.output}")
    if validation_warnings:
        print(f"Coverage warnings: {len(validation_warnings)}")
        for warning in validation_warnings[:50]:
            print(f"- {warning}")
    if validation_errors:
        print(f"Validation errors: {len(validation_errors)}")
        for error in validation_errors[:50]:
            print(f"- {error}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
