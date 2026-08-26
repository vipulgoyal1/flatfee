#!/usr/bin/env python3
"""Download, transform, and validate Zillow data for the Flat Fee city pages.

This script intentionally does not modify HTML files. It writes raw downloads to
data/zillow/raw/ (gitignored) and the compact, reviewable output to
data/zillow/processed/city-pages.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "zillow-sources.json"
DEFAULT_CITY_CONFIG = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "zillow" / "raw"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "zillow" / "processed" / "city-pages.json"
DATE_COLUMN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RETURN_PERIODS = (1, 3, 5, 10, 20, 25)
USER_AGENT = "FlatFeeRealtor-ZillowDataUpdater/1.0"


class PipelineError(RuntimeError):
    """Raised when source data or generated output fails a safety check."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def date_columns(fieldnames: Iterable[str] | None) -> list[str]:
    if not fieldnames:
        raise PipelineError("CSV has no header row")
    dates = sorted(column for column in fieldnames if DATE_COLUMN.fullmatch(column))
    if not dates:
        raise PipelineError("CSV has no YYYY-MM-DD data columns")
    return dates


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        number = float(stripped)
    except ValueError as exc:
        raise PipelineError(f"Expected a number, received {value!r}") from exc
    if not math.isfinite(number):
        return None
    return number


def parse_integer(value: str | None) -> int | None:
    number = parse_number(value)
    return None if number is None else int(number)


def comparison_date(dates: list[str], latest_date: str, years: int) -> str | None:
    year = int(latest_date[:4]) - years
    month_prefix = f"{year:04d}-{latest_date[5:7]}-"
    matches = [date for date in dates if date.startswith(month_prefix)]
    return matches[-1] if matches else None


def latest_complete_date(
    dates: list[str], rows: Iterable[dict[str, str]], metric_name: str
) -> str:
    rows = list(rows)
    if not rows:
        raise PipelineError(f"No rows supplied for {metric_name}")
    for date in reversed(dates):
        if all(parse_number(row.get(date)) is not None for row in rows):
            return date
    raise PipelineError(f"{metric_name} has no date with values for all configured cities")


def return_metrics(row: dict[str, str], dates: list[str], latest_date: str) -> dict[str, dict[str, Any]]:
    latest_value = parse_number(row.get(latest_date))
    metrics: dict[str, dict[str, Any]] = {}
    for years in RETURN_PERIODS:
        prior_date = comparison_date(dates, latest_date, years)
        prior_value = parse_number(row.get(prior_date)) if prior_date else None
        if latest_value is None or prior_value is None or prior_value <= 0:
            total_return = None
            cagr = None
        else:
            ratio = latest_value / prior_value
            total_return = round((ratio - 1.0) * 100.0, 4)
            cagr = round((ratio ** (1.0 / years) - 1.0) * 100.0, 4)
        metrics[f"{years}y"] = {
            "comparison_date": prior_date,
            "total_return_pct": total_return,
            "cagr_pct": cagr,
        }
    return metrics


def inspect_csv(path: Path, required_columns: list[str]) -> dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"Missing source file: {path}")
    sha256 = hashlib.sha256()
    with path.open("rb") as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            sha256.update(chunk)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise PipelineError(f"Empty CSV: {path}") from exc
        missing = sorted(set(required_columns) - set(header))
        if missing:
            raise PipelineError(f"{path.name} is missing required columns: {', '.join(missing)}")
        dates = date_columns(header)
        row_count = sum(1 for row in reader if row)
    if row_count == 0:
        raise PipelineError(f"CSV contains no data rows: {path}")
    try:
        display_path = str(path.relative_to(REPO_ROOT))
    except ValueError:
        display_path = str(path)
    return {
        "path": display_path,
        "bytes": path.stat().st_size,
        "sha256": sha256.hexdigest(),
        "rows": row_count,
        "first_date": dates[0],
        "latest_date": dates[-1],
        "date_columns": len(dates),
    }


def download_one(source: dict[str, Any], raw_dir: Path, timeout: int) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / source["filename"]
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    print(f"Downloading {source['id']} -> {target}", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temp.open("wb") as handle:
            response_headers = {
                "content_length": parse_integer(response.headers.get("Content-Length")),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
            downloaded_bytes = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded_bytes += len(chunk)
        expected_bytes = response_headers["content_length"]
        if expected_bytes is not None and downloaded_bytes != expected_bytes:
            raise PipelineError(
                f"Incomplete download for {source['id']}: expected {expected_bytes:,} bytes, "
                f"received {downloaded_bytes:,}"
            )
        inspected = inspect_csv(temp, source["required_columns"])
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    try:
        inspected["path"] = str(target.relative_to(REPO_ROOT))
    except ValueError:
        inspected["path"] = str(target)
    inspected.update(
        {
            "id": source["id"],
            "url": source["url"],
            "filename": source["filename"],
            "downloaded_at": utc_now(),
            "http": response_headers,
        }
    )
    print(
        f"  {inspected['rows']:,} rows; {inspected['bytes']:,} bytes; latest {inspected['latest_date']}",
        flush=True,
    )
    return inspected


def enabled_sources(source_config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [source for source in source_config.get("sources", []) if source.get("enabled", True)]
    if not sources:
        raise PipelineError("No enabled Zillow sources are configured")
    ids = [source["id"] for source in sources]
    if len(ids) != len(set(ids)):
        raise PipelineError("Duplicate source id in Zillow source configuration")
    return sources


def download_sources(source_config_path: Path, raw_dir: Path, timeout: int) -> dict[str, Any]:
    source_config = read_json(source_config_path)
    results = [download_one(source, raw_dir, timeout) for source in enabled_sources(source_config)]
    results_by_id = {item["id"]: item for item in results}
    alignment_results: dict[str, str] = {}
    for group in source_config.get("alignment_groups", []):
        missing = [source_id for source_id in group["source_ids"] if source_id not in results_by_id]
        if missing:
            raise PipelineError(
                f"Alignment group {group['id']} references disabled or missing sources: {missing}"
            )
        latest_dates = {results_by_id[source_id]["latest_date"] for source_id in group["source_ids"]}
        if len(latest_dates) != 1:
            details = ", ".join(
                f"{source_id}={results_by_id[source_id]['latest_date']}"
                for source_id in group["source_ids"]
            )
            raise PipelineError(f"Alignment group {group['id']} has different latest months: {details}")
        alignment_results[group["id"]] = next(iter(latest_dates))
    manifest = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "latest_by_source": {item["id"]: item["latest_date"] for item in results},
        "aligned_latest_dates": alignment_results,
        "sources": results,
    }
    write_json_atomic(raw_dir / "download-manifest.json", manifest)
    return manifest


def read_city_rows(path: Path, wanted_region_ids: set[int]) -> tuple[list[str], dict[int, dict[str, str]]]:
    found: dict[int, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        dates = date_columns(reader.fieldnames)
        for row in reader:
            region_id = parse_integer(row.get("RegionID"))
            if region_id in wanted_region_ids:
                if region_id in found:
                    raise PipelineError(f"Duplicate City RegionID {region_id} in {path.name}")
                found[region_id] = row
    missing = sorted(wanted_region_ids - set(found))
    if missing:
        raise PipelineError(f"City source is missing configured RegionIDs: {missing}")
    return dates, found


def read_neighborhood_rows(
    path: Path, city_names: set[str], state: str, required_latest_date: str
) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        dates = date_columns(reader.fieldnames)
        if dates[-1] != required_latest_date:
            raise PipelineError(
                f"Neighborhood latest date {dates[-1]} does not match City latest date {required_latest_date}"
            )
        ten_year_date = comparison_date(dates, required_latest_date, 10)
        if not ten_year_date:
            raise PipelineError("Neighborhood source lacks a 10-year comparison date")
        for row in reader:
            city = row.get("City", "").strip()
            if row.get("State", "").strip() != state or city not in city_names:
                continue
            if parse_number(row.get(required_latest_date)) is None:
                continue
            if parse_number(row.get(ten_year_date)) is None:
                continue
            grouped[city].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: (parse_integer(row.get("SizeRank")) or sys.maxsize, row.get("RegionName", "")))
    return dates, grouped


def compact_series(row: dict[str, str], dates: list[str]) -> dict[str, list[Any]]:
    return {
        "dates": dates,
        "values": [round(value, 2) if (value := parse_number(row.get(date))) is not None else None for date in dates],
    }


def compact_neighborhood(row: dict[str, str], dates: list[str], latest_date: str) -> dict[str, Any]:
    latest_value = parse_number(row.get(latest_date))
    return {
        "region_id": parse_integer(row.get("RegionID")),
        "size_rank": parse_integer(row.get("SizeRank")),
        "name": row.get("RegionName", "").strip(),
        "county": row.get("CountyName", "").strip(),
        "metro": row.get("Metro", "").strip(),
        "typical_home_value": round(latest_value, 2) if latest_value is not None else None,
        "returns": return_metrics(row, dates, latest_date),
    }


def validate_city_identity(
    row: dict[str, str], city: dict[str, Any], expected_state: str, source_id: str
) -> None:
    region_id = int(city["region_id"])
    if row.get("RegionName", "").strip() != city["name"]:
        raise PipelineError(
            f"{source_id}: RegionID {region_id} is {row.get('RegionName')!r}, "
            f"not configured city {city['name']!r}"
        )
    if row.get("State", "").strip() != expected_state:
        raise PipelineError(f"{source_id}: {city['name']} did not resolve to {expected_state}")
    if row.get("CountyName", "").strip() != city["county"]:
        raise PipelineError(
            f"{source_id}: county mismatch for {city['name']}: "
            f"source={row.get('CountyName')!r}, config={city['county']!r}"
        )


def compact_market_metric(
    row: dict[str, str], dates: list[str], latest_date: str, unit: str
) -> dict[str, Any]:
    latest_value = parse_number(row.get(latest_date))
    if latest_value is None:
        raise PipelineError(
            f"{row.get('RegionName', 'City')} has no {unit} value for {latest_date}"
        )
    display_value: int | float
    if unit in ("USD", "days"):
        display_value = round(latest_value)
    else:
        display_value = round(latest_value, 2)
    series_dates = [date for date in dates if date <= latest_date]
    return {
        "as_of": latest_date,
        "value": round(latest_value, 2),
        "display_value": display_value,
        "unit": unit,
        "series": compact_series(row, series_dates),
    }


def build_processed_data(
    source_config_path: Path, city_config_path: Path, raw_dir: Path, output_path: Path
) -> dict[str, Any]:
    source_config = read_json(source_config_path)
    city_config = read_json(city_config_path)
    cities = city_config.get("cities", [])
    if len(cities) != 43:
        raise PipelineError(f"Expected 43 configured city pages, found {len(cities)}")

    source_by_id = {source["id"]: source for source in enabled_sources(source_config)}
    required_source_ids = (
        "city_sfr_zhvi",
        "neighborhood_sfr_zhvi",
        "city_sfr_median_sale_price",
        "city_median_days_to_pending",
    )
    for required_id in required_source_ids:
        if required_id not in source_by_id:
            raise PipelineError(f"Missing required source configuration: {required_id}")

    city_source = source_by_id["city_sfr_zhvi"]
    neighborhood_source = source_by_id["neighborhood_sfr_zhvi"]
    sale_price_source = source_by_id["city_sfr_median_sale_price"]
    days_pending_source = source_by_id["city_median_days_to_pending"]
    city_path = raw_dir / city_source["filename"]
    neighborhood_path = raw_dir / neighborhood_source["filename"]
    sale_price_path = raw_dir / sale_price_source["filename"]
    days_pending_path = raw_dir / days_pending_source["filename"]

    wanted_ids = {int(city["region_id"]) for city in cities}
    city_dates, city_rows = read_city_rows(city_path, wanted_ids)
    sale_price_dates, sale_price_rows = read_city_rows(sale_price_path, wanted_ids)
    days_pending_dates, days_pending_rows = read_city_rows(days_pending_path, wanted_ids)
    latest_date = latest_complete_date(city_dates, city_rows.values(), "City SFR ZHVI")
    sale_price_date = latest_complete_date(
        sale_price_dates, sale_price_rows.values(), "City SFR median sale price"
    )
    days_pending_date = latest_complete_date(
        days_pending_dates, days_pending_rows.values(), "City median days to pending"
    )
    neighborhood_dates, neighborhood_rows = read_neighborhood_rows(
        neighborhood_path,
        {city["name"] for city in cities},
        city_config.get("state", "CA"),
        latest_date,
    )

    raw_manifest_path = raw_dir / "download-manifest.json"
    raw_manifest = read_json(raw_manifest_path) if raw_manifest_path.exists() else None

    output_cities: dict[str, Any] = {}
    expected_state = city_config.get("state", "CA")
    for city in cities:
        region_id = int(city["region_id"])
        row = city_rows[region_id]
        sale_price_row = sale_price_rows[region_id]
        days_pending_row = days_pending_rows[region_id]
        validate_city_identity(row, city, expected_state, city_source["id"])
        validate_city_identity(
            sale_price_row, city, expected_state, sale_price_source["id"]
        )
        validate_city_identity(
            days_pending_row, city, expected_state, days_pending_source["id"]
        )
        latest_value = parse_number(row.get(latest_date))
        if latest_value is None:
            raise PipelineError(f"{city['name']} has no value for latest common month {latest_date}")
        neighborhoods = [
            compact_neighborhood(item, neighborhood_dates, latest_date)
            for item in neighborhood_rows.get(city["name"], [])
        ]
        output_cities[city["slug"]] = {
            "page": city["page"],
            "region_id": region_id,
            "name": city["name"],
            "state": row.get("State", "").strip(),
            "county": row.get("CountyName", "").strip(),
            "metro": row.get("Metro", "").strip(),
            "size_rank": parse_integer(row.get("SizeRank")),
            "as_of": latest_date,
            "typical_home_value": round(latest_value, 2),
            "returns": return_metrics(row, city_dates, latest_date),
            "series": compact_series(row, [date for date in city_dates if date <= latest_date]),
            "market_snapshot": {
                "median_sale_price": compact_market_metric(
                    sale_price_row, sale_price_dates, sale_price_date, "USD"
                ),
                "median_days_to_pending": compact_market_metric(
                    days_pending_row, days_pending_dates, days_pending_date, "days"
                ),
            },
            "neighborhoods": neighborhoods,
        }

    payload = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "metric": "Zillow Home Value Index (ZHVI)",
        "housing_type": "Single-family residences",
        "series_type": "Smoothed, seasonally adjusted, monthly",
        "as_of": latest_date,
        "data_dates": {
            "city_sfr_zhvi": latest_date,
            "neighborhood_sfr_zhvi": latest_date,
            "city_sfr_median_sale_price": sale_price_date,
            "city_median_days_to_pending": days_pending_date,
        },
        "metric_definitions": {
            "typical_home_value": {
                "source_id": city_source["id"],
                "housing_type": city_source["housing_type"],
                "series_type": city_source["series_type"],
            },
            "median_sale_price": {
                "source_id": sale_price_source["id"],
                "housing_type": sale_price_source["housing_type"],
                "series_type": sale_price_source["series_type"],
            },
            "median_days_to_pending": {
                "source_id": days_pending_source["id"],
                "housing_type": days_pending_source["housing_type"],
                "series_type": days_pending_source["series_type"],
                "definition": days_pending_source["definition"],
            },
        },
        "return_periods_years": list(RETURN_PERIODS),
        "neighborhood_inclusion_rule": "California, exact City match, latest value present, 10-year comparison value present",
        "attribution": "Data provided by Zillow Group",
        "research_page": source_config["research_page"],
        "source_manifest": raw_manifest,
        "summary": {
            "city_pages": len(output_cities),
            "cities_with_complete_market_snapshot": sum(
                1
                for city in output_cities.values()
                if city["market_snapshot"]["median_sale_price"]["value"] is not None
                and city["market_snapshot"]["median_days_to_pending"]["value"] is not None
            ),
            "cities_with_neighborhoods": sum(1 for city in output_cities.values() if city["neighborhoods"]),
            "neighborhood_rows": sum(len(city["neighborhoods"]) for city in output_cities.values()),
        },
        "cities": output_cities,
    }
    write_json_atomic(output_path, payload)
    print(
        f"Built {output_path}: {payload['summary']['city_pages']} cities, "
        f"{payload['summary']['neighborhood_rows']} neighborhood rows; "
        f"ZHVI {latest_date}, sale price {sale_price_date}, days pending {days_pending_date}",
        flush=True,
    )
    return payload


def validate_processed_data(city_config_path: Path, output_path: Path) -> dict[str, Any]:
    city_config = read_json(city_config_path)
    payload = read_json(output_path)
    errors: list[str] = []
    configured = city_config.get("cities", [])
    cities = payload.get("cities", {})

    if len(configured) != 43:
        errors.append(f"city manifest has {len(configured)} entries, expected 43")
    if len(cities) != 43:
        errors.append(f"processed output has {len(cities)} cities, expected 43")
    if payload.get("schema_version") != 2:
        errors.append("processed output schema_version is not 2")

    expected_slugs = {city["slug"] for city in configured}
    if set(cities) != expected_slugs:
        errors.append("processed city slugs do not exactly match the city manifest")
    if len({city["page"] for city in configured}) != len(configured):
        errors.append("city manifest contains duplicate HTML page names")
    if len({int(city["region_id"]) for city in configured}) != len(configured):
        errors.append("city manifest contains duplicate RegionIDs")

    expected_date = payload.get("as_of")
    if not expected_date or not DATE_COLUMN.fullmatch(expected_date):
        errors.append("processed output has an invalid as_of date")
    data_dates = payload.get("data_dates", {})
    required_data_dates = {
        "city_sfr_zhvi",
        "neighborhood_sfr_zhvi",
        "city_sfr_median_sale_price",
        "city_median_days_to_pending",
    }
    if set(data_dates) != required_data_dates:
        errors.append("processed output data_dates do not cover all four required sources")
    if data_dates.get("city_sfr_zhvi") != expected_date:
        errors.append("top-level as_of does not match City SFR ZHVI date")
    if data_dates.get("neighborhood_sfr_zhvi") != expected_date:
        errors.append("City and Neighborhood ZHVI dates differ")

    for configured_city in configured:
        slug = configured_city["slug"]
        city = cities.get(slug)
        if not city:
            continue
        if city.get("page") != configured_city["page"]:
            errors.append(f"{slug}: page name differs from manifest")
        if city.get("as_of") != expected_date:
            errors.append(f"{slug}: as_of differs from common date")
        if city.get("typical_home_value") is None:
            errors.append(f"{slug}: missing current ZHVI")
        series = city.get("series", {})
        dates = series.get("dates", [])
        values = series.get("values", [])
        if not dates or dates[-1] != expected_date:
            errors.append(f"{slug}: series does not end at common date")
        if len(dates) != len(values):
            errors.append(f"{slug}: series dates and values have different lengths")
        if values and values[-1] != city.get("typical_home_value"):
            errors.append(f"{slug}: current value does not match final series point")
        returns = city.get("returns", {})
        if set(returns) != {f"{years}y" for years in RETURN_PERIODS}:
            errors.append(f"{slug}: return periods are incomplete")
        market_snapshot = city.get("market_snapshot", {})
        for metric_key, source_id, expected_unit in (
            ("median_sale_price", "city_sfr_median_sale_price", "USD"),
            ("median_days_to_pending", "city_median_days_to_pending", "days"),
        ):
            metric = market_snapshot.get(metric_key, {})
            metric_date = data_dates.get(source_id)
            if metric.get("as_of") != metric_date:
                errors.append(f"{slug}: {metric_key} date differs from shared metric date")
            if metric.get("value") is None or metric.get("display_value") is None:
                errors.append(f"{slug}: {metric_key} is missing a current value")
            if metric.get("unit") != expected_unit:
                errors.append(f"{slug}: {metric_key} has the wrong unit")
            metric_series = metric.get("series", {})
            metric_dates = metric_series.get("dates", [])
            metric_values = metric_series.get("values", [])
            if not metric_dates or metric_dates[-1] != metric_date:
                errors.append(f"{slug}: {metric_key} series does not end at its as-of date")
            if len(metric_dates) != len(metric_values):
                errors.append(f"{slug}: {metric_key} series lengths differ")
            if metric_values and metric_values[-1] != metric.get("value"):
                errors.append(f"{slug}: {metric_key} current value differs from its series")
        neighborhoods = city.get("neighborhoods", [])
        ranks = [row.get("size_rank") or sys.maxsize for row in neighborhoods]
        if ranks != sorted(ranks):
            errors.append(f"{slug}: neighborhoods are not ordered by Zillow SizeRank")
        if any(row.get("typical_home_value") is None for row in neighborhoods):
            errors.append(f"{slug}: neighborhood output contains a missing latest value")

    for city in configured:
        if not (REPO_ROOT / city["page"]).exists():
            errors.append(f"configured HTML page does not exist: {city['page']}")

    if errors:
        raise PipelineError("Validation failed:\n- " + "\n- ".join(errors))
    summary = payload.get("summary", {})
    if summary.get("cities_with_complete_market_snapshot") != 43:
        raise PipelineError("Validation failed: market snapshot is not complete for all 43 cities")
    print(
        f"Validated {len(cities)} city records, complete market snapshots, and "
        f"{summary.get('neighborhood_rows', 0)} neighborhood rows; "
        f"ZHVI {expected_date}, sale price {data_dates.get('city_sfr_median_sale_price')}, "
        f"days pending {data_dates.get('city_median_days_to_pending')}",
        flush=True,
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("download", "build", "validate", "all"), help="Pipeline stage to run"
    )
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITY_CONFIG)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in ("download", "all"):
            download_sources(args.sources, args.raw_dir, args.timeout)
        if args.command in ("build", "all"):
            build_processed_data(args.sources, args.cities, args.raw_dir, args.output)
        if args.command in ("validate", "all"):
            validate_processed_data(args.cities, args.output)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, csv.Error, PipelineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
