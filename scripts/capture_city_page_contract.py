#!/usr/bin/env python3
"""Capture the protected city-page copy and neighborhood membership from Git.

This is a maintenance tool, not part of a normal Zillow data refresh. Run it
only after the owner approves a copy or neighborhood-membership change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CITY_CONFIG = REPO_ROOT / "config" / "city-pages.json"
DEFAULT_OUTPUT = REPO_ROOT / "config" / "city-page-copy-contract.json"
DEFAULT_DATA = REPO_ROOT / "data" / "zillow" / "processed" / "city-pages.json"


def git_text(ref: str, page: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{page}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8")


def comment_pattern(label: str) -> str:
    return rf"<!--\s*=+\s*{label}\s*=+\s*-->"


STATS_RE = re.compile(
    comment_pattern(r"STATS \+ CHART")
    + r'\s*<section class="sf-stats-section">.*?</section>',
    re.DOTALL,
)
NEIGHBORHOOD_RE = re.compile(
    comment_pattern("NEIGHBORHOOD RANKINGS")
    + r".*?(?="
    + comment_pattern("FAQ")
    + r")",
    re.DOTALL,
)
STAT_VALUE_RE = re.compile(
    r'(<div class="stat-val">).*?(</div>\s*<div class="stat-label">)',
    re.DOTALL,
)
COUNT_RE = re.compile(
    r"(?P<prefix>\b(?:top\s+)?)\d+(?P<suffix>\s+neighborhoods?\b)",
    re.IGNORECASE,
)
RAW_DATA_RE = re.compile(r"const rawData\s*=\s*\[(.*?)\];", re.DOTALL)
CITY_NAME_RE = re.compile(r'\{"city"\s*:\s*("(?:[^"\\]|\\.)*")')
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


def normalize_stats_copy(block: str) -> str:
    return STAT_VALUE_RE.sub(r"\1<DATA_VALUE>\2", block).replace("\r\n", "\n")


def normalize_neighborhood_copy(block: str) -> str:
    block = COUNT_RE.sub(r"\g<prefix><DATA_COUNT>\g<suffix>", block)
    return block.replace("\r\n", "\n")


def normalize_page_copy(text: str) -> str:
    text = MLS_SECTION_RE.sub("\n", text)
    text = MLS_SCRIPT_BLOCK_RE.sub("\n", text)
    text = MLS_CSS_RE.sub("\n", text)
    text = SCRIPT_STYLE_RE.sub("", text)
    text = STAT_VALUE_RE.sub(r"\1<DATA_VALUE>\2", text)
    text = COUNT_RE.sub(r"\g<prefix><DATA_COUNT>\g<suffix>", text)
    text = text.replace("\r\n", "\n")
    return re.sub(r"\n{2,}", "\n", text)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_neighborhood_names(text: str) -> list[str]:
    match = RAW_DATA_RE.search(text)
    if not match:
        return []
    return [json.loads(value) for value in CITY_NAME_RE.findall(match.group(1))]


def exactly_one(pattern: re.Pattern[str], text: str, label: str) -> str:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}; found {len(matches)}")
    return matches[0].group(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--ref")
    source.add_argument("--working-tree", action="store_true")
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITY_CONFIG)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--adopt-current-neighborhoods",
        default="",
        help="Comma-separated approved city slugs whose current Zillow neighborhood list should be adopted.",
    )
    args = parser.parse_args()

    city_config = json.loads(args.cities.read_text(encoding="utf-8"))
    existing = (
        json.loads(args.output.read_text(encoding="utf-8"))
        if args.output.exists()
        else {}
    )
    ref = args.ref or "HEAD"
    revision = (
        existing.get("source_revision")
        if args.working_tree and existing.get("source_revision")
        else subprocess.run(
            ["git", "rev-parse", ref],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    processed = json.loads(args.data.read_text(encoding="utf-8"))
    adopt_slugs = {
        slug.strip()
        for slug in args.adopt_current_neighborhoods.split(",")
        if slug.strip()
    }
    unknown_adoptions = adopt_slugs - {city["slug"] for city in city_config["cities"]}
    if unknown_adoptions:
        raise RuntimeError(f"Unknown adoption slugs: {sorted(unknown_adoptions)}")

    cities: dict[str, object] = {}
    for configured_city in city_config["cities"]:
        page = configured_city["page"]
        slug = configured_city["slug"]
        text = (
            (REPO_ROOT / page).read_text(encoding="utf-8")
            if args.working_tree
            else git_text(ref, page)
        )
        stats = exactly_one(STATS_RE, text, f"stats section in {page}")
        neighborhood_match = NEIGHBORHOOD_RE.search(text)
        if slug in adopt_slugs:
            names = [row["name"] for row in processed["cities"][slug]["neighborhoods"]]
        elif args.working_tree:
            names = existing.get("cities", {}).get(slug, {}).get("neighborhoods", [])
        else:
            names = extract_neighborhood_names(text)
        cities[slug] = {
            "page": page,
            "page_copy_sha256": digest(normalize_page_copy(text)),
            "stats_copy_sha256": digest(normalize_stats_copy(stats)),
            "neighborhood_section": neighborhood_match is not None,
            "neighborhood_copy_sha256": (
                digest(normalize_neighborhood_copy(neighborhood_match.group(0)))
                if neighborhood_match
                else None
            ),
            "neighborhoods": names,
        }

    contract = {
        "schema_version": 1,
        "source_revision": revision,
        "capture_source": "working_tree" if args.working_tree else ref,
        "policy": (
            "Preserve approved city-page editorial copy. Normal refreshes may change only "
            "numeric stat values, chart/table data, and the numeric neighborhood count."
        ),
        "source_name_overrides": existing.get(
            "source_name_overrides",
            {"sunnyvale": {"Washington": "Washington Park"}},
        ),
        "cities": cities,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output.relative_to(REPO_ROOT)} for {len(cities)} pages "
        f"from {'working tree' if args.working_tree else revision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
