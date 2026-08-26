#!/usr/bin/env python3
"""Refresh ranking-page numbers from the official Zillow ZHVI downloads.

The updater preserves page copy, links, filters, geography labels, and existing
record membership. Missing legacy records receive null numeric values rather
than stale values. The two regional HTML files are changed only inside their
existing ``rawData`` arrays; the two national pages read generated data assets.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from zillow_pipeline import (  # noqa: E402
    RETURN_PERIODS,
    date_columns,
    parse_integer,
    parse_number,
    return_metrics,
)


CITY_SOURCE = REPO_ROOT / "data" / "zillow" / "raw" / "City_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv"
NEIGHBORHOOD_SOURCE = REPO_ROOT / "data" / "zillow" / "raw" / "Neighborhood_zhvi_uc_sfr_sm_sa_month.csv"
CITY_ASSET = REPO_ROOT / "assets" / "data" / "us_metro_city_data.js"
NEIGHBORHOOD_ASSET = REPO_ROOT / "assets" / "data" / "us_neighborhoods_data.js"
MANIFEST_PATH = REPO_ROOT / "data" / "zillow" / "processed" / "ranking-pages-manifest.json"
HUB_PAGE = REPO_ROOT / "Appreciation-Rankings-Hub.html"
REGIONAL_PAGES = (
    REPO_ROOT / "Bay-Area-City-Appreciation-Ranking.html",
    REPO_ROOT / "Southern-CA-City-Appreciation-Ranking.html",
)
CITY_PREFIX = "window.US_METRO_CITY_DATA="
NEIGHBORHOOD_PREFIX = "window.US_NEIGHBORHOOD_DATA="
RAW_DATA_PATTERN = re.compile(r"(\s*const\s+rawData\s*=\s*)(\[.*?\])(\s*;)", re.DOTALL)
HUB_DATE_PATTERN = re.compile(r"Data updated through [A-Za-z]+ \d{1,2}, \d{4}\.")
METRIC_FIELDS = tuple(
    field
    for years in RETURN_PERIODS
    for field in (f"total_return_{years}y", f"cagr_{years}y")
)
NUMERIC_FIELDS = ("typical_price",) + METRIC_FIELDS
DEFAULT_TOP_CITY_MAX_SIZE_RANK = 132

# Approved display-name compatibility already used by the city-page updater.
NEIGHBORHOOD_SOURCE_NAME_OVERRIDES = {
    ("Washington", "CA", "Sunnyvale"): "Washington Park",
}


class RankingUpdateError(RuntimeError):
    """Raised when a protected-copy or source-data condition fails."""


def read_source(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise RankingUpdateError(f"Missing Zillow source: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        dates = date_columns(reader.fieldnames)
        rows = list(reader)
    if not rows:
        raise RankingUpdateError(f"Zillow source has no rows: {path}")
    return rows, dates


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_js_asset(path: Path, prefix: str) -> dict[str, list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith(prefix):
        raise RankingUpdateError(f"Unexpected JavaScript data prefix in {path.name}")
    payload = text[len(prefix) :].strip()
    if not payload.endswith(";"):
        raise RankingUpdateError(f"Missing JavaScript terminator in {path.name}")
    return json.loads(payload[:-1])


def dump_js_asset(prefix: str, payload: dict[str, list[dict[str, Any]]]) -> str:
    return prefix + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"


def numeric_record(source_row: dict[str, str], dates: list[str], latest_date: str) -> dict[str, Any]:
    latest_value = parse_number(source_row.get(latest_date))
    metrics = return_metrics(source_row, dates, latest_date)
    output: dict[str, Any] = {
        # Match the city-page pipeline, which stores source values at cents
        # before applying whole-dollar display rounding.
        "typical_price": round(round(latest_value, 2)) if latest_value is not None else None,
    }
    for years in RETURN_PERIODS:
        period = metrics[f"{years}y"]
        output[f"total_return_{years}y"] = period["total_return_pct"]
        output[f"cagr_{years}y"] = period["cagr_pct"]
    return output


def clear_numeric_record(record: dict[str, Any]) -> None:
    for field in NUMERIC_FIELDS:
        record[field] = None


def apply_numeric_record(
    record: dict[str, Any], source_row: dict[str, str], dates: list[str], latest_date: str
) -> None:
    record.update(numeric_record(source_row, dates, latest_date))


def city_signature(payload: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[tuple[str, str, str]]]]:
    return [
        (group, [(row["city"], row["county"], row["state"]) for row in rows])
        for group, rows in payload.items()
    ]


def neighborhood_signature(payload: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[str]]]:
    return [(group, [row["city"] for row in rows]) for group, rows in payload.items()]


def update_city_asset(
    original: dict[str, list[dict[str, Any]]],
    source_rows: list[dict[str, str]],
    dates: list[str],
    latest_date: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    index = {(row["RegionName"], row["State"], row["CountyName"]): row for row in source_rows}
    name_state_index: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        name_state_index[(row["RegionName"], row["State"])].append(row)

    output = copy.deepcopy(original)
    missing: list[dict[str, Any]] = []
    matched = 0
    compatibility_matches = 0

    for metro, rows in output.items():
        for record in rows:
            key = (record["city"], record["state"], record["county"])
            source = index.get(key)
            if source is None:
                candidates = name_state_index.get((record["city"], record["state"]), [])
                old_rank = int(record["sizeRank"])
                rank_matches = [row for row in candidates if parse_integer(row.get("SizeRank")) == old_rank]
                if len(rank_matches) == 1:
                    source = rank_matches[0]
                    compatibility_matches += 1

            if source is None:
                missing.append(
                    {
                        "metro": metro,
                        "city": record["city"],
                        "state": record["state"],
                        "county": record["county"],
                        "size_rank": record["sizeRank"],
                    }
                )
                clear_numeric_record(record)
                continue

            matched += 1
            record["sizeRank"] = parse_integer(source.get("SizeRank"))
            apply_numeric_record(record, source, dates, latest_date)

    top_missing = [row for row in missing if int(row["size_rank"]) <= DEFAULT_TOP_CITY_MAX_SIZE_RANK]
    if top_missing:
        raise RankingUpdateError(f"Top U.S. city rows are missing from Zillow: {top_missing}")
    if city_signature(output) != city_signature(original):
        raise RankingUpdateError("U.S. city geography labels or record order changed")
    return output, {
        "records": sum(len(rows) for rows in output.values()),
        "matched": matched,
        "compatibility_matches": compatibility_matches,
        "unavailable_legacy_records": missing,
    }


def choose_duplicate_candidate(record: dict[str, Any], candidates: list[dict[str, str]]) -> dict[str, str]:
    old_rank = int(record["sizeRank"])
    ranked = sorted(
        candidates,
        key=lambda row: abs((parse_integer(row.get("SizeRank")) or 10**9) - old_rank),
    )
    if len(ranked) > 1:
        first = abs((parse_integer(ranked[0].get("SizeRank")) or 10**9) - old_rank)
        second = abs((parse_integer(ranked[1].get("SizeRank")) or 10**9) - old_rank)
        if first == second:
            raise RankingUpdateError(
                f"Cannot disambiguate neighborhood {record['city']!r} at size rank {old_rank}"
            )
    return ranked[0]


def update_neighborhood_asset(
    original: dict[str, list[dict[str, Any]]],
    source_rows: list[dict[str, str]],
    dates: list[str],
    latest_date: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    index: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        index[(row["RegionName"], row["State"], row["City"])].append(row)

    output = copy.deepcopy(original)
    missing: list[dict[str, Any]] = []
    matched = 0
    duplicate_matches = 0
    compatibility_matches = 0

    for group, rows in output.items():
        city, state = group.rsplit(", ", 1)
        for record in rows:
            display_name = record["city"]
            source_name = NEIGHBORHOOD_SOURCE_NAME_OVERRIDES.get(
                (display_name, state, city), display_name
            )
            candidates = index.get((source_name, state, city), [])
            if not candidates:
                missing.append(
                    {
                        "city_group": group,
                        "neighborhood": display_name,
                        "size_rank": record["sizeRank"],
                    }
                )
                clear_numeric_record(record)
                continue
            if source_name != display_name:
                compatibility_matches += 1
            source = candidates[0]
            if len(candidates) > 1:
                source = choose_duplicate_candidate(record, candidates)
                duplicate_matches += 1
            matched += 1
            record["sizeRank"] = parse_integer(source.get("SizeRank"))
            apply_numeric_record(record, source, dates, latest_date)

    if any(row["city_group"] == "San Jose, CA" for row in missing):
        raise RankingUpdateError("The default San Jose neighborhood ranking has unavailable data")
    if neighborhood_signature(output) != neighborhood_signature(original):
        raise RankingUpdateError("U.S. neighborhood labels or record order changed")
    return output, {
        "records": sum(len(rows) for rows in output.values()),
        "matched": matched,
        "compatibility_matches": compatibility_matches,
        "duplicate_name_matches": duplicate_matches,
        "unavailable_legacy_records": missing,
    }


def parse_regional_rows(page_text: str, page_name: str) -> tuple[re.Match[str], list[dict[str, Any]]]:
    matches = list(RAW_DATA_PATTERN.finditer(page_text))
    if len(matches) != 1:
        raise RankingUpdateError(f"Expected one rawData array in {page_name}; found {len(matches)}")
    match = matches[0]
    return match, json.loads(match.group(2))


def transform_regional_page(
    page_text: str,
    page_name: str,
    source_index: dict[tuple[str, str], list[dict[str, str]]],
    dates: list[str],
    latest_date: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    match, rows = parse_regional_rows(page_text, page_name)
    old_rows = copy.deepcopy(rows)
    for record in rows:
        candidates = source_index.get((record["city"], "CA"), [])
        if len(candidates) != 1:
            raise RankingUpdateError(
                f"{page_name}: {record['city']} has {len(candidates)} current Zillow matches"
            )
        apply_numeric_record(record, candidates[0], dates, latest_date)

    if [row["city"] for row in rows] != [row["city"] for row in old_rows]:
        raise RankingUpdateError(f"{page_name}: regional city membership or order changed")

    indent = "        "
    replacement = match.group(1) + "[\n"
    replacement += ",\n".join(
        indent + json.dumps(row, ensure_ascii=False, separators=(", ", ": ")) for row in rows
    )
    replacement += "\n    ]" + match.group(3)
    updated = page_text[: match.start()] + replacement + page_text[match.end() :]

    protected_before = page_text[: match.start()] + "<RANKING_NUMERIC_DATA>" + page_text[match.end() :]
    new_match = RAW_DATA_PATTERN.search(updated)
    if new_match is None:
        raise RankingUpdateError(f"{page_name}: generated rawData array is invalid")
    protected_after = updated[: new_match.start()] + "<RANKING_NUMERIC_DATA>" + updated[new_match.end() :]
    if protected_before != protected_after:
        raise RankingUpdateError(f"{page_name}: protected HTML copy changed")
    return updated, old_rows, rows


def transform_hub_date(page_text: str, latest_date: str) -> str:
    year, month, day = latest_date.split("-")
    month_name = {
        "01": "Jan",
        "02": "Feb",
        "03": "Mar",
        "04": "Apr",
        "05": "May",
        "06": "Jun",
        "07": "Jul",
        "08": "Aug",
        "09": "Sep",
        "10": "Oct",
        "11": "Nov",
        "12": "Dec",
    }[month]
    replacement = f"Data updated through {month_name} {int(day)}, {year}."
    matches = HUB_DATE_PATTERN.findall(page_text)
    if len(matches) != 1:
        raise RankingUpdateError(
            f"Expected one ranking-hub data date; found {len(matches)}"
        )
    updated = HUB_DATE_PATTERN.sub(replacement, page_text, count=1)
    if HUB_DATE_PATTERN.sub("<RANKING_DATA_DATE>", page_text, count=1) != HUB_DATE_PATTERN.sub(
        "<RANKING_DATA_DATE>", updated, count=1
    ):
        raise RankingUpdateError("Ranking hub changed outside its data-date value")
    return updated


def review_flags(scope: str, old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for old, new in zip(old_rows, new_rows):
        label = new.get("city", "unknown")
        old_price = old.get("typical_price")
        new_price = new.get("typical_price")
        if old_price and new_price:
            change = round((new_price / old_price - 1) * 100, 2)
            if abs(change) > 15:
                flags.append({"scope": scope, "record": label, "flag": "price_change_pct", "value": change})
        old_1y = old.get("total_return_1y")
        new_1y = new.get("total_return_1y")
        if old_1y is not None and new_1y is not None:
            change = round(new_1y - old_1y, 2)
            if abs(change) > 10:
                flags.append({"scope": scope, "record": label, "flag": "one_year_return_change_pp", "value": change})
        if new_1y is not None and abs(new_1y) > 50:
            flags.append({"scope": scope, "record": label, "flag": "one_year_return_outlier", "value": new_1y})
    return flags


def flatten(payload: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row for rows in payload.values() for row in rows]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def build_update() -> tuple[dict[Path, str], dict[str, Any], dict[str, Any]]:
    city_rows, city_dates = read_source(CITY_SOURCE)
    neighborhood_rows, neighborhood_dates = read_source(NEIGHBORHOOD_SOURCE)
    if city_dates[-1] != neighborhood_dates[-1]:
        raise RankingUpdateError(
            f"City and neighborhood Zillow dates differ: {city_dates[-1]} vs {neighborhood_dates[-1]}"
        )
    latest_date = city_dates[-1]

    original_city = load_js_asset(CITY_ASSET, CITY_PREFIX)
    original_neighborhood = load_js_asset(NEIGHBORHOOD_ASSET, NEIGHBORHOOD_PREFIX)
    updated_city, city_report = update_city_asset(original_city, city_rows, city_dates, latest_date)
    updated_neighborhood, neighborhood_report = update_neighborhood_asset(
        original_neighborhood, neighborhood_rows, neighborhood_dates, latest_date
    )

    outputs: dict[Path, str] = {
        CITY_ASSET: dump_js_asset(CITY_PREFIX, updated_city),
        NEIGHBORHOOD_ASSET: dump_js_asset(NEIGHBORHOOD_PREFIX, updated_neighborhood),
    }
    flags = review_flags("us_cities", flatten(original_city), flatten(updated_city))
    flags += review_flags(
        "us_neighborhoods", flatten(original_neighborhood), flatten(updated_neighborhood)
    )

    city_name_index: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in city_rows:
        city_name_index[(row["RegionName"], row["State"])].append(row)
    regional_report: dict[str, Any] = {}
    for page_path in REGIONAL_PAGES:
        original_page = page_path.read_text(encoding="utf-8-sig")
        updated_page, old_rows, new_rows = transform_regional_page(
            original_page,
            page_path.name,
            city_name_index,
            city_dates,
            latest_date,
        )
        outputs[page_path] = updated_page
        regional_report[page_path.name] = {"records": len(new_rows), "matched": len(new_rows)}
        flags += review_flags(page_path.name, old_rows, new_rows)

    hub_text = HUB_PAGE.read_text(encoding="utf-8-sig")
    outputs[HUB_PAGE] = transform_hub_date(hub_text, latest_date)

    manifest = {
        "schema_version": 1,
        "as_of": latest_date,
        "periods_years": list(RETURN_PERIODS),
        "sources": {
            "city_sfr_zhvi": {
                "path": str(CITY_SOURCE.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256(CITY_SOURCE),
                "rows": len(city_rows),
                "first_date": city_dates[0],
                "latest_date": city_dates[-1],
            },
            "neighborhood_sfr_zhvi": {
                "path": str(NEIGHBORHOOD_SOURCE.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256(NEIGHBORHOOD_SOURCE),
                "rows": len(neighborhood_rows),
                "first_date": neighborhood_dates[0],
                "latest_date": neighborhood_dates[-1],
            },
        },
        "outputs": {
            "us_cities": city_report,
            "us_neighborhoods": neighborhood_report,
            "regional_pages": regional_report,
        },
    }
    outputs[MANIFEST_PATH] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    report = {
        "as_of": latest_date,
        "changed_files": [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path, text in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8-sig") != text
        ],
        "city_asset": city_report,
        "neighborhood_asset": neighborhood_report,
        "regional_pages": regional_report,
        "hub_data_date": latest_date,
        "review_flags": flags,
    }
    return outputs, manifest, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Report stale generated ranking data")
    mode.add_argument("--write", action="store_true", help="Apply the coordinated numeric update")
    args = parser.parse_args()

    try:
        outputs, _manifest, report = build_update()
        if args.write:
            for path, text in outputs.items():
                if not path.exists() or path.read_text(encoding="utf-8-sig") != text:
                    write_atomic(path, text)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.check and report["changed_files"]:
            return 1
        return 0
    except (OSError, ValueError, KeyError, RankingUpdateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
