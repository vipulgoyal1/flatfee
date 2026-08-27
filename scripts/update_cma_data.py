#!/usr/bin/env python3
"""Build and validate the California city ZHVI dataset used by CMA.html."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    REPO_ROOT
    / "data"
    / "zillow"
    / "raw"
    / "City_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv"
)
DEFAULT_OUTPUT = REPO_ROOT / "assets" / "data" / "ca_cities_zhvi_data.js"
DEFAULT_HTML = REPO_ROOT / "CMA.html"
DATE_COLUMN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CMA_SCRIPT_PATTERN = re.compile(
    r"(<script\s+src=([\"'])assets/data/ca_cities_zhvi_data\.js)(?:\?v=\d{6})?(\2\s*></script>)"
)
CMA_ADJUSTED_LABEL_PATTERN = re.compile(
    r'(<span class="metric-label">)[A-Z][a-z]{2} \d{4}( Adjusted (?:\$/sf|Range)</span>)'
)
MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
JS_PREFIX = "window.CA_CITIES_ZHVI_DATA="
JS_SUFFIX = ";\n"
MINIMUM_CA_CITIES = 800


class CmaDataError(RuntimeError):
    """Raised when the CMA source or generated data fails validation."""


def date_columns(fieldnames: Iterable[str] | None) -> list[str]:
    if not fieldnames:
        raise CmaDataError("CSV has no header row")
    dates = sorted(column for column in fieldnames if DATE_COLUMN.fullmatch(column))
    if not dates:
        raise CmaDataError("CSV has no YYYY-MM-DD data columns")
    return dates


def parse_number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise CmaDataError(f"Expected a number, received {value!r}") from exc
    return round(number, 2) if math.isfinite(number) else None


def parse_rank(value: str | None, city_name: str) -> int:
    number = parse_number(value)
    if number is None or number < 0 or not number.is_integer():
        raise CmaDataError(f"Invalid SizeRank for {city_name}: {value!r}")
    return int(number)


def validate_payload(payload: dict[str, Any], minimum_cities: int = MINIMUM_CA_CITIES) -> None:
    dates = payload.get("dates")
    cities = payload.get("cities")
    if not isinstance(dates, list) or not dates:
        raise CmaDataError("Generated payload has no dates")
    if dates != sorted(set(dates)):
        raise CmaDataError("Generated dates are duplicated or out of order")
    if not isinstance(cities, list) or len(cities) < minimum_cities:
        count = len(cities) if isinstance(cities, list) else 0
        raise CmaDataError(
            f"Generated payload has only {count} California cities; expected at least {minimum_cities}"
        )

    city_ids: set[str] = set()
    for city in cities:
        if not isinstance(city, dict):
            raise CmaDataError("Generated city row is not an object")
        city_id = city.get("id")
        if not isinstance(city_id, str) or not city_id:
            raise CmaDataError("Generated city row has no id")
        if city_id in city_ids:
            raise CmaDataError(f"Duplicate California RegionID: {city_id}")
        city_ids.add(city_id)
        for field in ("name", "county", "metro"):
            if not isinstance(city.get(field), str):
                raise CmaDataError(f"City {city_id} has an invalid {field}")
        if not isinstance(city.get("rank"), int):
            raise CmaDataError(f"City {city_id} has an invalid rank")
        values = city.get("values")
        if not isinstance(values, list) or len(values) != len(dates):
            raise CmaDataError(f"City {city_id} values do not align with the date columns")
        if not any(isinstance(value, (int, float)) for value in values):
            raise CmaDataError(f"City {city_id} has no usable ZHVI values")


def build_payload(source: Path, minimum_cities: int = MINIMUM_CA_CITIES) -> dict[str, Any]:
    if not source.exists():
        raise CmaDataError(f"Missing Zillow source file: {source}")

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "RegionID",
            "SizeRank",
            "RegionName",
            "State",
            "Metro",
            "CountyName",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise CmaDataError(f"Source CSV is missing columns: {', '.join(missing)}")
        dates = date_columns(reader.fieldnames)
        cities: list[dict[str, Any]] = []

        for row in reader:
            if row.get("State") != "CA":
                continue
            city_id = (row.get("RegionID") or "").strip()
            city_name = (row.get("RegionName") or "").strip()
            county = (row.get("CountyName") or "").strip()
            metro = (row.get("Metro") or "").strip()
            if not city_id or not city_name or not county:
                raise CmaDataError(
                    f"California source row is missing RegionID, RegionName, or CountyName: {row!r}"
                )
            cities.append(
                {
                    "id": city_id,
                    "rank": parse_rank(row.get("SizeRank"), city_name),
                    "name": city_name,
                    "county": county,
                    "metro": metro,
                    "values": [parse_number(row.get(date)) for date in dates],
                }
            )

    cities.sort(key=lambda city: (city["rank"], city["name"].casefold(), city["id"]))
    payload = {"dates": dates, "cities": cities}
    validate_payload(payload, minimum_cities)
    return payload


def render_javascript(payload: dict[str, Any]) -> str:
    return JS_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ) + JS_SUFFIX


def parse_javascript(text: str) -> dict[str, Any]:
    if not text.startswith(JS_PREFIX) or not text.endswith(JS_SUFFIX):
        raise CmaDataError("CMA asset has an unexpected JavaScript wrapper")
    try:
        payload = json.loads(text[len(JS_PREFIX) : -len(JS_SUFFIX)])
    except json.JSONDecodeError as exc:
        raise CmaDataError(f"CMA asset contains invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CmaDataError("CMA asset payload is not an object")
    return payload


def render_cma_html(text: str, latest_date: str) -> str:
    matches = list(CMA_SCRIPT_PATTERN.finditer(text))
    if len(matches) != 1:
        raise CmaDataError(
            f"Expected one CMA dataset script tag in CMA.html, found {len(matches)}"
        )
    version = latest_date[:7].replace("-", "")
    match = matches[0]
    replacement = f"{match.group(1)}?v={version}{match.group(3)}"
    updated = text[: match.start()] + replacement + text[match.end() :]

    label_matches = list(CMA_ADJUSTED_LABEL_PATTERN.finditer(updated))
    if len(label_matches) != 2:
        raise CmaDataError(
            f"Expected two dataset-month labels in CMA.html, found {len(label_matches)}"
        )
    year = int(latest_date[:4])
    month = int(latest_date[5:7])
    month_label = f"{MONTH_ABBREVIATIONS[month - 1]} {year}"
    return CMA_ADJUSTED_LABEL_PATTERN.sub(
        lambda label_match: f"{label_match.group(1)}{month_label}{label_match.group(2)}",
        updated,
    )


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def summary(
    payload: dict[str, Any],
    source: Path,
    output: Path,
    html: Path,
    asset_current: bool,
    html_current: bool,
) -> dict[str, Any]:
    cities = payload["cities"]
    return {
        "source": display_path(source),
        "output": display_path(output),
        "html": display_path(html),
        "first_date": payload["dates"][0],
        "latest_date": payload["dates"][-1],
        "date_count": len(payload["dates"]),
        "california_city_count": len(cities),
        "cities_with_latest_value": sum(city["values"][-1] is not None for city in cities),
        "asset_current": asset_current,
        "html_current": html_current,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Report whether the CMA asset is current")
    action.add_argument("--write", action="store_true", help="Write the current CMA asset")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--minimum-cities", type=int, default=MINIMUM_CA_CITIES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_payload(args.source, args.minimum_cities)
        expected = render_javascript(payload)
        if not args.html.exists():
            raise CmaDataError(f"Missing CMA page: {args.html}")
        existing_html = args.html.read_text(encoding="utf-8")
        expected_html = render_cma_html(existing_html, payload["dates"][-1])
        asset_current = args.output.exists() and args.output.read_text(encoding="utf-8") == expected
        html_current = existing_html == expected_html
        if args.write and not asset_current:
            write_text_atomic(args.output, expected)
            asset_current = True
        if args.write and not html_current:
            write_text_atomic(args.html, expected_html)
            html_current = True
        print(
            json.dumps(
                summary(
                    payload,
                    args.source,
                    args.output,
                    args.html,
                    asset_current,
                    html_current,
                ),
                indent=2,
            )
        )
        return 0 if asset_current and html_current else 1
    except (CmaDataError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
