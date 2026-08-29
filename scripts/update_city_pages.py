#!/usr/bin/env python3
"""Generate consistent Zillow-driven content for all 43 Flat Fee city pages.

The default mode is a read-only check. Use --write only after reviewing the
pipeline output and the reported page count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CITY_CONFIG = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_COPY_CONTRACT = REPO_ROOT / "config" / "city-page-copy-contract.json"
DEFAULT_DATA = REPO_ROOT / "data" / "zillow" / "processed" / "city-pages.json"
DEFAULT_ASSET_DIR = REPO_ROOT / "assets" / "data" / "city-pages"
CSS_LINK = '  <link rel="stylesheet" href="assets/theme/css/city-data.css">'
SHARED_SCRIPT = '<script src="assets/js/city-page-data.js"></script>'


class UpdateError(RuntimeError):
    """Raised when a page does not match the safe generated-section contract."""


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent, suffix=".tmp") as handle:
        handle.write(text.encode("utf-8"))
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def page_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def format_currency(value: int | float) -> str:
    return f"${round(value):,}"


def format_return(value: int | float | None) -> str:
    if value is None:
        return "N/A"
    arrow_class = "arrow-up" if value >= 0 else "arrow-down"
    arrow_code = "&#9650;" if value >= 0 else "&#9660;"
    return f'<span class="{arrow_class}">{arrow_code}</span>&nbsp;{abs(value):.1f}%'


def comment_pattern(label: str) -> str:
    return rf"<!--\s*=+\s*{label}\s*=+\s*-->"


STATS_RE = re.compile(
    comment_pattern(r"STATS \+ CHART")
    + r'\s*<section class="sf-stats-section">.*?</section>',
    re.DOTALL,
)
NEIGHBORHOOD_RE = re.compile(
    comment_pattern("NEIGHBORHOOD RANKINGS") + r".*?(?=" + comment_pattern("FAQ") + r")",
    re.DOTALL,
)
LEGACY_EXTERNAL_DATA_RE = re.compile(
    r'<script src="assets/data/[^"\r\n]+_zhvi_series\.js"></script>'
)
LEGACY_INLINE_DATA_RE = re.compile(
    r"<script>window\.[A-Z0-9_]+_ZHVI_SERIES\s*=\s*.*?</script>", re.DOTALL
)
CURRENT_DATA_INCLUDE_RE = re.compile(
    r'<script src="assets/data/city-pages/[^"\r\n]+\.js"></script>\s*'
    r'<script src="assets/js/city-page-data\.js"></script>'
)
LEGACY_INLINE_SCRIPTS_RE = re.compile(
    r"\s*<!-- Neighborhood Table Script -->.*?<!-- Chart Script -->.*?</script>\s*",
    re.DOTALL,
)
STAT_VALUE_RE = re.compile(
    r'(?P<prefix><div class="stat-val">).*?'
    r'(?P<middle></div>\s*<div class="stat-label">(?P<label>[^<]+)</div>)',
    re.DOTALL,
)
NEIGHBORHOOD_COUNT_RE = re.compile(
    r"(?P<prefix>\b(?:top\s+)?)\d+(?P<suffix>\s+neighborhoods?\b)",
    re.IGNORECASE,
)
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
MLS_SECTION_RE = re.compile(
    r'\s*(?:<!--\s*=+\s*CITY MLS DASHBOARD\s*=+\s*-->\s*)?'
    r'<section class="sj-mls-dashboard"[^>]*>.*?</section>',
    re.DOTALL,
)
MLS_SCRIPT_BLOCK_RE = re.compile(
    r"\s*<!-- CITY MLS CHARTS -->.*?<!-- END CITY MLS CHARTS -->\s*",
    re.DOTALL,
)
MLS_CSS_RE = re.compile(
    r'\s*<link rel="stylesheet" href="assets/css/city-mls-dashboard\.css">'
)


def stat_value(label: str, city: dict[str, Any]) -> str:
    label = label.strip()
    if label == "YoY Price Change":
        return format_return(city["returns"]["1y"]["total_return_pct"])
    period_match = re.fullmatch(r"(\d+)-Year Price Change", label)
    if period_match:
        period = f"{period_match.group(1)}y"
        if period not in city["returns"]:
            raise UpdateError(f"Unsupported price-change period in label: {label!r}")
        return format_return(city["returns"][period]["total_return_pct"])
    if label == "Typical Home Value":
        return format_currency(city["typical_home_value"])
    if label == "Median Sale Price":
        return format_currency(city["market_snapshot"]["median_sale_price"]["display_value"])
    if label in {"Median Days on Market", "Median Days to Pending"}:
        return str(round(city["market_snapshot"]["median_days_to_pending"]["display_value"]))
    raise UpdateError(f"Unknown stat label: {label!r}")


def update_stats_values(block: str, city: dict[str, Any]) -> str:
    count = 0

    def replacement(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return (
            match.group("prefix")
            + stat_value(match.group("label"), city)
            + match.group("middle")
        )

    updated = STAT_VALUE_RE.sub(replacement, block)
    if count != 6:
        raise UpdateError(f"Expected six numeric stat values; found {count}")
    return updated


def normalize_stats_copy(block: str) -> str:
    return STAT_VALUE_RE.sub(
        lambda match: match.group("prefix") + "<DATA_VALUE>" + match.group("middle"),
        block,
    ).replace("\r\n", "\n")


def normalize_neighborhood_copy(block: str) -> str:
    return NEIGHBORHOOD_COUNT_RE.sub(
        lambda match: match.group("prefix") + "<DATA_COUNT>" + match.group("suffix"),
        block,
    ).replace("\r\n", "\n")


def normalize_page_copy(text: str) -> str:
    # The MLS dashboard is protected and updated by
    # scripts/update_aculist_city_pages.py. Excluding only its exact owned
    # markers keeps the independent Zillow and MLS workflows composable.
    text = MLS_SECTION_RE.sub("\n", text)
    text = MLS_SCRIPT_BLOCK_RE.sub("\n", text)
    text = MLS_CSS_RE.sub("\n", text)
    text = SCRIPT_STYLE_RE.sub("", text)
    text = STAT_VALUE_RE.sub(
        lambda match: match.group("prefix") + "<DATA_VALUE>" + match.group("middle"),
        text,
    )
    text = NEIGHBORHOOD_COUNT_RE.sub(
        lambda match: match.group("prefix") + "<DATA_COUNT>" + match.group("suffix"),
        text,
    )
    text = text.replace("\r\n", "\n")
    return re.sub(r"\n{2,}", "\n", text)


def copy_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def update_neighborhood_count(block: str, count: int) -> str:
    updated, substitutions = NEIGHBORHOOD_COUNT_RE.subn(
        lambda match: match.group("prefix") + str(count) + match.group("suffix"),
        block,
    )
    if substitutions != 1:
        raise UpdateError(
            f"Expected one numeric neighborhood count in protected copy; found {substitutions}"
        )
    return updated


def select_neighborhoods(
    slug: str, city: dict[str, Any], copy_contract: dict[str, Any]
) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str]]:
    page_contract = copy_contract["cities"][slug]
    approved_names = page_contract["neighborhoods"]
    overrides = copy_contract.get("source_name_overrides", {}).get(slug, {})
    current_by_name: dict[str, dict[str, Any]] = {}
    for row in city["neighborhoods"]:
        current_by_name.setdefault(row["name"], row)

    selected: list[tuple[str, dict[str, Any]]] = []
    missing: list[str] = []
    selected_source_names: set[str] = set()
    for display_name in approved_names:
        source_name = overrides.get(display_name, display_name)
        row = current_by_name.get(source_name)
        if row is None:
            missing.append(display_name)
            continue
        selected.append((display_name, row))
        selected_source_names.add(source_name)

    not_added = [
        row["name"]
        for row in city["neighborhoods"]
        if row["name"] not in selected_source_names
    ]
    return selected, missing, not_added


def compact_neighborhoods(
    selected: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for rank, (display_name, row) in enumerate(selected, start=1):
        item: dict[str, Any] = {
            "rank": rank,
            "zillow_size_rank": row["size_rank"],
            "name": display_name,
            "typical_price": round(row["typical_home_value"]),
        }
        for period in ("1y", "3y", "5y", "10y", "20y", "25y"):
            item[f"total_return_{period}"] = row["returns"][period]["total_return_pct"]
            item[f"cagr_{period}"] = row["returns"][period]["cagr_pct"]
        output.append(item)
    return output


def build_city_asset(
    slug: str,
    city: dict[str, Any],
    payload: dict[str, Any],
    selected_neighborhoods: list[tuple[str, dict[str, Any]]],
) -> str:
    data = {
        "schema_version": 1,
        "slug": slug,
        "name": city["name"],
        "page": city["page"],
        "data_dates": payload["data_dates"],
        "chart": {
            "dates": city["series"]["dates"],
            "prices": city["series"]["values"],
        },
        "neighborhoods": compact_neighborhoods(selected_neighborhoods),
    }
    encoded = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    return f"window.CITY_PAGE_DATA = {encoded};\n"


def transform_page(
    text: str,
    slug: str,
    city: dict[str, Any],
    payload: dict[str, Any],
    page_contract: dict[str, Any],
    selected_neighborhoods: list[tuple[str, dict[str, Any]]],
) -> str:
    newline = page_newline(text)
    stats_matches = list(STATS_RE.finditer(text))
    if len(stats_matches) != 1:
        raise UpdateError(f"Expected exactly one stats section; found {len(stats_matches)}")
    stats_block = stats_matches[0].group(0)
    stats_hash = copy_digest(normalize_stats_copy(stats_block))
    if stats_hash != page_contract["stats_copy_sha256"]:
        raise UpdateError("Protected stats copy differs from the approved copy contract")
    text = STATS_RE.sub(lambda _match: update_stats_values(stats_block, city), text)

    neighborhood_matches = list(NEIGHBORHOOD_RE.finditer(text))
    should_show_neighborhoods = bool(
        page_contract["neighborhood_section"] and selected_neighborhoods
    )
    if should_show_neighborhoods:
        if len(neighborhood_matches) != 1:
            raise UpdateError(
                "Approved neighborhood copy is missing; a data refresh may not create new copy"
            )
        neighborhood_block = neighborhood_matches[0].group(0)
        neighborhood_hash = copy_digest(normalize_neighborhood_copy(neighborhood_block))
        if neighborhood_hash != page_contract["neighborhood_copy_sha256"]:
            raise UpdateError("Protected neighborhood copy differs from the approved copy contract")
        updated_block = update_neighborhood_count(
            neighborhood_block, len(selected_neighborhoods)
        )
        text = NEIGHBORHOOD_RE.sub(lambda _match: updated_block, text)
    else:
        if page_contract["neighborhood_section"]:
            raise UpdateError(
                "Approved neighborhood section has no current Zillow rows; "
                "a routine data refresh may not remove its visible copy"
            )
        if neighborhood_matches:
            raise UpdateError(
                "Unapproved neighborhood section is present; a routine data "
                "refresh may not remove or adopt visible copy"
            )

    current_include = (
        f'<script src="assets/data/city-pages/{slug}.js"></script>{newline}{SHARED_SCRIPT}'
    )
    current_matches = len(CURRENT_DATA_INCLUDE_RE.findall(text))
    legacy_external_matches = len(LEGACY_EXTERNAL_DATA_RE.findall(text))
    legacy_inline_matches = len(LEGACY_INLINE_DATA_RE.findall(text))
    include_match_count = current_matches + legacy_external_matches + legacy_inline_matches
    if include_match_count != 1:
        raise UpdateError(
            "Expected exactly one current or legacy city-data include; "
            f"found current={current_matches}, external={legacy_external_matches}, inline={legacy_inline_matches}"
        )
    if current_matches:
        text = CURRENT_DATA_INCLUDE_RE.sub(lambda _match: current_include, text)
    elif legacy_external_matches:
        text = LEGACY_EXTERNAL_DATA_RE.sub(lambda _match: current_include, text)
    else:
        text = LEGACY_INLINE_DATA_RE.sub(lambda _match: current_include, text)

    legacy_script_matches = len(LEGACY_INLINE_SCRIPTS_RE.findall(text))
    if legacy_script_matches > 1:
        raise UpdateError(f"Expected at most one legacy table/chart script block; found {legacy_script_matches}")
    if legacy_script_matches == 1:
        text = LEGACY_INLINE_SCRIPTS_RE.sub(newline, text)

    css_count = text.count(CSS_LINK)
    if css_count == 0:
        theme_link = '  <link rel="stylesheet" href="assets/theme/css/style.css">'
        if text.count(theme_link) != 1:
            raise UpdateError(f"Expected one theme CSS link; found {text.count(theme_link)}")
        text = text.replace(theme_link, theme_link + newline + CSS_LINK)
    elif css_count != 1:
        raise UpdateError(f"Expected at most one city-data CSS link; found {css_count}")

    approved_page_hash = page_contract.get("page_copy_sha256")
    if approved_page_hash and copy_digest(normalize_page_copy(text)) != approved_page_hash:
        raise UpdateError("Page copy or approved structure differs from the copy contract")

    return text


def validate_payload(city_config: dict[str, Any], payload: dict[str, Any]) -> None:
    configured = city_config.get("cities", [])
    processed = payload.get("cities", {})
    if len(configured) != 43 or len(processed) != 43:
        raise UpdateError(
            f"Expected 43 configured and processed cities; found {len(configured)} and {len(processed)}"
        )
    expected_slugs = {city["slug"] for city in configured}
    if set(processed) != expected_slugs:
        raise UpdateError("Processed city slugs do not match the 43-page manifest")
    if payload.get("summary", {}).get("cities_with_complete_market_snapshot") != 43:
        raise UpdateError("Not all 43 cities have a complete market snapshot")


def read_git_page(ref: str, page: str) -> str:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{page}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise UpdateError(f"Could not read {page} from Git ref {ref!r}") from exc
    return result.stdout.decode("utf-8")


def run_update(
    city_config_path: Path,
    copy_contract_path: Path,
    data_path: Path,
    asset_dir: Path,
    write: bool,
    source_ref: str | None = None,
) -> dict[str, Any]:
    city_config = read_json(city_config_path)
    copy_contract = read_json(copy_contract_path)
    payload = read_json(data_path)
    validate_payload(city_config, payload)
    if set(copy_contract.get("cities", {})) != {
        city["slug"] for city in city_config["cities"]
    }:
        raise UpdateError("Copy-contract slugs do not match the 43-page manifest")

    changed_pages: list[str] = []
    changed_assets: list[str] = []
    page_outputs: list[tuple[Path, str]] = []
    asset_outputs: list[tuple[Path, str]] = []
    missing_neighborhood_rows: dict[str, list[str]] = {}
    new_neighborhood_rows_not_added: dict[str, list[str]] = {}
    pages_with_neighborhood_sections = 0

    for configured_city in city_config["cities"]:
        slug = configured_city["slug"]
        city = payload["cities"][slug]
        page_contract = copy_contract["cities"][slug]
        selected, missing, not_added = select_neighborhoods(slug, city, copy_contract)
        if page_contract["neighborhood_section"] and selected:
            pages_with_neighborhood_sections += 1
        if missing:
            missing_neighborhood_rows[configured_city["page"]] = missing
        if not_added:
            new_neighborhood_rows_not_added[configured_city["page"]] = not_added

        page_path = REPO_ROOT / configured_city["page"]
        original = page_path.read_bytes().decode("utf-8")
        source = read_git_page(source_ref, configured_city["page"]) if source_ref else original
        try:
            updated = transform_page(
                source,
                slug,
                city,
                payload,
                page_contract,
                selected,
            )
        except UpdateError as exc:
            raise UpdateError(f"{configured_city['page']}: {exc}") from exc
        if updated != original:
            changed_pages.append(configured_city["page"])
            page_outputs.append((page_path, updated))

        asset_path = asset_dir / f"{slug}.js"
        asset_text = build_city_asset(slug, city, payload, selected)
        existing_asset = asset_path.read_text(encoding="utf-8") if asset_path.exists() else None
        if asset_text != existing_asset:
            changed_assets.append(str(asset_path.relative_to(REPO_ROOT)))
            asset_outputs.append((asset_path, asset_text))

    if write:
        for path, text in page_outputs + asset_outputs:
            write_text_atomic(path, text)

    result = {
        "mode": "write" if write else "check",
        "copy_source_ref": source_ref,
        "configured_pages": 43,
        "changed_pages": changed_pages,
        "changed_assets": changed_assets,
        "data_dates": payload["data_dates"],
        "cities_with_source_neighborhood_data": payload["summary"]["cities_with_neighborhoods"],
        "cities_with_neighborhood_sections": pages_with_neighborhood_sections,
        "cities_without_neighborhood_sections": 43 - pages_with_neighborhood_sections,
        "neighborhood_rows_missing_from_zillow": missing_neighborhood_rows,
        "new_zillow_neighborhood_rows_not_added": new_neighborhood_rows_not_added,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Report stale generated content (default)")
    mode.add_argument("--write", action="store_true", help="Apply generated page and asset updates")
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITY_CONFIG)
    parser.add_argument("--copy-contract", type=Path, default=DEFAULT_COPY_CONTRACT)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument(
        "--source-ref",
        help=(
            "One-time copy restoration source, such as HEAD. Omit during normal data refreshes."
        ),
    )
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_update(
            args.cities,
            args.copy_contract,
            args.data,
            args.asset_dir,
            write=args.write,
            source_ref=args.source_ref,
        )
    except (OSError, json.JSONDecodeError, UpdateError) as exc:
        print(f"ERROR: {exc}")
        return 2

    report = json.dumps(result, indent=2)
    print(report)
    if args.report:
        write_text_atomic(args.report, report + "\n")
    if not args.write and (result["changed_pages"] or result["changed_assets"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
