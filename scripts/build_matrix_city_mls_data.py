#!/usr/bin/env python3
"""Build city-page MLS assets from the dated MLSListings Matrix archive.

The Matrix source is long-format monthly CSV data captured for Residential /
Single Family Home listings. Only reviewed source anomalies are changed, and
they are changed to null rather than estimated.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_SOURCE = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
    r"\Matrix-2026-08-29-22-cities"
)
DEFAULT_OUTPUT = REPO_ROOT / "assets" / "data" / "mls"

TARGET_SLUGS = {
    "anaheim", "bakersfield", "chula-vista", "elk-grove", "fresno",
    "glendale", "huntington-beach", "irvine", "long-beach",
    "los-angeles", "modesto", "pasadena", "riverside", "roseville",
    "sacramento", "san-diego", "san-luis-obispo", "santa-ana",
    "stockton", "ventura",
}

# Standard pages align with the January 2016 start used by the existing MLS
# dashboards. These cities use the reviewed start of their reliable
# reciprocal-MLS coverage instead of displaying a known source break.
START_MONTHS = {
    "bakersfield": "2021-01",
    "san-diego": "2023-01",
}

# A metric can begin later than the page's other series when older source data
# is unusable. This keeps the good history in the other charts.
SERIES_START_MONTHS = {
    "los-angeles": {"daysOnMarket": "2020-01"},
}

SERIES = {
    "salePrice": {
        "file": "06 Sale Price - Average + Median.csv",
        "column": "Sale Price, Median", "decimals": 0,
        "aggregation": "mean", "minimum": 50_000, "maximum": 10_000_000,
    },
    "daysOnMarket": {
        "file": "03 Days to Sell - Average + Median.csv",
        "column": "Days to Sell, Median", "decimals": 1,
        "aggregation": "mean", "minimum": 0, "maximum": 730,
    },
    "saleToList": {
        "file": "08 Sale to List + Sale to Original Price Ratios.csv",
        "column": "Sale Price to List Price Ratio", "decimals": 2,
        "aggregation": "mean", "minimum": 50, "maximum": 200,
    },
    "closedSales": {
        "file": "09 Closed Sales - Dollar Volume + Number.csv",
        "column": "Sales, Number of", "decimals": 0,
        "aggregation": "sum", "minimum": 0, "maximum": 20_000,
    },
    "pricePerSqFt": {
        "file": "07 Price Per SqFt + Months of Inventory.csv",
        "column": "Price/SqFt Ratio", "decimals": 1,
        "aggregation": "mean", "minimum": 25, "maximum": 5_000,
    },
}

# Reviewed isolated Matrix errors. The surrounding months return to their
# normal range, so these source values are represented as gaps, not estimates.
KNOWN_ANOMALIES = {
    "anaheim": {"daysOnMarket": {"2016-01", "2016-02"}},
    "bakersfield": {
        "pricePerSqFt": {"2020-01", "2021-06", "2023-01"},
        "saleToList": {"2021-08"},
    },
    "chula-vista": {"daysOnMarket": {"2016-01", "2016-02"}},
    "fresno": {
        "pricePerSqFt": {"2024-05", "2026-05"},
        "saleToList": {"2018-03", "2018-09", "2023-02"},
    },
    "glendale": {"daysOnMarket": {"2016-02"}},
    "huntington-beach": {"daysOnMarket": {"2016-01", "2016-02"}},
    "irvine": {"daysOnMarket": {"2016-01", "2016-02"}},
    "long-beach": {"daysOnMarket": {"2016-01", "2016-02"}},
    "los-angeles": {"pricePerSqFt": {"2018-04"}},
    "modesto": {"pricePerSqFt": {"2025-04"}},
    "riverside": {
        "daysOnMarket": {"2016-01", "2016-02"},
        "saleToList": {"2023-10"},
    },
    "sacramento": {"pricePerSqFt": {"2020-12"}},
    "san-luis-obispo": {
        "daysOnMarket": {"2016-01", "2016-02", "2016-03"},
    },
    "santa-ana": {"daysOnMarket": {"2016-01", "2016-02"}},
    "stockton": {"pricePerSqFt": {"2018-11", "2025-03"}},
    "ventura": {"pricePerSqFt": {"2022-09", "2025-02"}},
}

VALIDATION_OVERRIDES: dict[str, dict[str, dict[str, float]]] = {}


def month_key(label: str) -> str:
    return datetime.strptime(label, "%b %Y").strftime("%Y-%m")


def parse_number(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    return None if not cleaned else float(cleaned)


def rounded(value: float | None, decimals: int) -> float | int | None:
    if value is None:
        return None
    return int(round(value)) if decimals == 0 else round(value, decimals)


def month_range(first: str, latest: str) -> list[str]:
    current = datetime.strptime(first, "%Y-%m")
    end = datetime.strptime(latest, "%Y-%m")
    labels = []
    while current <= end:
        labels.append(current.strftime("%Y-%m"))
        current = datetime(
            current.year + (1 if current.month == 12 else 0),
            1 if current.month == 12 else current.month + 1,
            1,
        )
    return labels


def configured_targets() -> list[dict]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return [city for city in config["cities"] if city["slug"] in TARGET_SLUGS]


def read_metric(path: Path, column: str) -> dict[str, float | None]:
    if not path.exists():
        raise FileNotFoundError(f"Matrix CSV is missing: {path}")
    values = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or reader.fieldnames[0] != "Month":
            raise ValueError(f"Unexpected Matrix CSV structure: {path}")
        if column not in reader.fieldnames:
            raise ValueError(f"Column {column!r} is missing from {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Matrix CSV is empty: {path}")
    labels = [month_key(row["Month"]) for row in rows]
    if labels[0] != "2002-01" or labels != month_range(labels[0], labels[-1]):
        raise ValueError(f"Unexpected Matrix coverage in {path}")
    for row in rows:
        values[month_key(row["Month"])] = parse_number(row[column])
    return values


def median(values: list[float | int]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def validate_displayed_series(slug: str, series: dict) -> list[str]:
    """Reject obvious unreviewed errors that would be visible on a page."""
    errors = []
    sales = dict(zip(
        series["closedSales"]["labels"], series["closedSales"]["values"]
    ))

    dom = series["daysOnMarket"]
    for label, value in zip(dom["labels"], dom["values"]):
        if value == 0 and (sales.get(label) or 0) >= 20:
            errors.append(
                f"{slug}: daysOnMarket {label}=0 with "
                f"{sales[label]:g} closed sales"
            )

    for metric, relative_limit in (("pricePerSqFt", 0.50),):
        data = series[metric]
        values = data["values"]
        for index, value in enumerate(values):
            if value is None:
                continue
            neighbors = [
                candidate
                for candidate in (
                    values[max(0, index - 2):index]
                    + values[index + 1:index + 3]
                )
                if candidate is not None
            ]
            if len(neighbors) >= 2:
                baseline = median(neighbors)
                if baseline and abs(value / baseline - 1) >= relative_limit:
                    errors.append(
                        f"{slug}: {metric} {data['labels'][index]}={value:g} "
                        f"differs sharply from nearby median {baseline:g}"
                    )

    ratio = series["saleToList"]
    for index, value in enumerate(ratio["values"]):
        if value is None:
            continue
        neighbors = [
            candidate
            for candidate in (
                ratio["values"][max(0, index - 2):index]
                + ratio["values"][index + 1:index + 3]
            )
            if candidate is not None
        ]
        if len(neighbors) >= 2:
            baseline = median(neighbors)
            if abs(value - baseline) >= 12:
                errors.append(
                    f"{slug}: saleToList {ratio['labels'][index]}={value:g} "
                    f"differs sharply from nearby median {baseline:g}"
                )
    return errors


def build_city(
    source: Path, city: dict, latest_month: str
) -> tuple[dict, list[str]]:
    slug = city["slug"]
    start = START_MONTHS.get(slug, "2016-01")
    folder = source / city["name"]
    if not folder.is_dir():
        raise FileNotFoundError(f"Matrix city folder is missing: {folder}")

    errors = []
    output_series = {}
    excluded = {}
    for metric, definition in SERIES.items():
        metric_start = SERIES_START_MONTHS.get(slug, {}).get(metric, start)
        metric_labels = month_range(metric_start, latest_month)
        raw = read_metric(folder / definition["file"], definition["column"])
        if min(raw) != "2002-01" or max(raw) != latest_month:
            raise ValueError(
                f"Matrix coverage mismatch for {slug} {metric}: "
                f"{min(raw)} through {max(raw)}, expected 2002-01 through "
                f"{latest_month}"
            )
        anomaly_labels = KNOWN_ANOMALIES.get(slug, {}).get(metric, set())
        limits = {**definition, **VALIDATION_OVERRIDES.get(slug, {}).get(metric, {})}
        values = []
        for label in metric_labels:
            value = raw.get(label)
            if label in anomaly_labels:
                value = None
            elif value is not None and not (
                limits["minimum"] <= value <= limits["maximum"]
            ):
                errors.append(
                    f"{slug}: {metric} {label}={value:g} outside "
                    f"{limits['minimum']:g}..{limits['maximum']:g}"
                )
            values.append(rounded(value, definition["decimals"]))
        output_series[metric] = {
            "labels": metric_labels,
            "values": values,
            "aggregation": definition["aggregation"],
        }
        if anomaly_labels:
            excluded[metric] = sorted(
                label for label in anomaly_labels if label in metric_labels
            )

    reviewed = {
        (metric, label)
        for metric, metric_labels in KNOWN_ANOMALIES.get(slug, {}).items()
        for label in metric_labels
    }
    for metric, data in output_series.items():
        for label, value in zip(data["labels"], data["values"]):
            if value is None and (metric, label) not in reviewed:
                errors.append(f"{slug}: unreviewed missing {metric} value at {label}")
    errors.extend(validate_displayed_series(slug, output_series))

    payload = {
        "metadata": {
            "city": city["name"],
            "propertyType": "Single-family homes",
            "firstMonth": start,
            "latestMonth": latest_month,
            "method": (
                "No seasonal adjustment and no moving average. Quarterly and yearly "
                "views sum closed sales and take the arithmetic mean of the reported "
                "monthly values for all other metrics."
            ),
            "anomaliesExcluded": excluded,
            "seriesStartMonths": SERIES_START_MONTHS.get(slug, {}),
        },
        "series": output_series,
    }
    return payload, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--latest-month",
        help="Expected final source month in YYYY-MM form; inferred when omitted.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    targets = configured_targets()
    try:
        latest_month = args.latest_month or max(
            read_metric(
                args.source / targets[0]["name"] / SERIES["salePrice"]["file"],
                SERIES["salePrice"]["column"],
            )
        )
        datetime.strptime(latest_month, "%Y-%m")
    except (FileNotFoundError, ValueError) as exc:
        print("VALIDATION FAILED")
        print(f"- {exc}")
        return 1

    built = []
    errors = []
    for city in targets:
        try:
            payload, city_errors = build_city(args.source, city, latest_month)
            built.append((city, payload))
            errors.extend(city_errors)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Validated {len(built)} Matrix city assets.")
    for city, payload in built:
        metadata = payload["metadata"]
        print(f"- {city['name']}: {metadata['firstMonth']} through {metadata['latestMonth']}")

    if args.write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for city, payload in built:
            output = args.output_dir / f"{city['slug']}.js"
            output.write_text(
                "/* Generated by scripts/build_matrix_city_mls_data.py. */\n"
                "window.SAN_JOSE_MLS_V3_DATA="
                + json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                + ";\n",
                encoding="utf-8",
            )
        print(f"Wrote {len(built)} assets to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
