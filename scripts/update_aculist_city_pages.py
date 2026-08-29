#!/usr/bin/env python3
"""Add the San Jose MLS dashboard template to eligible Aculist city pages.

Only the Zillow section heading, Zillow graph heading, MLS section, MLS CSS
link, and MLS script tags are changed. All other page text is preserved.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "city-pages.json"
MLS_ASSET_DIR = REPO_ROOT / "assets" / "data" / "mls"
DEFAULT_SUMMARY = Path(
    r"C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data"
    r"\Aculist Downloads\2026-08-28\download-summary.json"
)

CSS_LINK = '<link rel="stylesheet" href="assets/css/city-mls-dashboard.css">'
SECTION_COMMENT = """<!-- =====================================================
     CITY MLS DASHBOARD
     ===================================================== -->"""
SCRIPT_TEMPLATE = """<!-- CITY MLS CHARTS -->
<script src="assets/data/mls/{slug}.js"></script>
<script src="assets/js/san-jose-mls-v3-charts.js"></script>
<!-- END CITY MLS CHARTS -->"""


class InstallationRequired(RuntimeError):
    """Raised when a routine refresh encounters a newly eligible page."""


def section_markup(city: str, first_month: str, latest_month: str) -> str:
    return f"""<section class="sj-mls-dashboard" id="cityMlsMarketData">
  <div class="container">
    <h2>{city} Trends from MLS</h2>

    <div class="mls-snapshot-grid" aria-label="{city} MLS latest monthly snapshot">
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Latest Data</span>
        <strong class="mls-snapshot-value" id="sjMlsV3LatestMonth">{latest_month}</strong>
      </div>
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Sale Price</span>
        <strong class="mls-snapshot-value" id="sjMlsV3SnapshotSalePrice">—</strong>
        <span class="mls-snapshot-change" id="sjMlsV3ChangeSalePrice">—</span>
      </div>
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Days on Market</span>
        <strong class="mls-snapshot-value" id="sjMlsV3SnapshotDaysOnMarket">—</strong>
        <span class="mls-snapshot-change" id="sjMlsV3ChangeDaysOnMarket">—</span>
      </div>
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Sale-to-List Performance</span>
        <strong class="mls-snapshot-value" id="sjMlsV3SnapshotSaleToList">—</strong>
        <span class="mls-snapshot-change" id="sjMlsV3ChangeSaleToList">—</span>
      </div>
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Closed-Sales Volume</span>
        <strong class="mls-snapshot-value" id="sjMlsV3SnapshotClosedSales">—</strong>
        <span class="mls-snapshot-change" id="sjMlsV3ChangeClosedSales">—</span>
      </div>
      <div class="mls-snapshot-card">
        <span class="mls-snapshot-label">Price per Square Foot</span>
        <strong class="mls-snapshot-value" id="sjMlsV3SnapshotPricePerSqFt">—</strong>
        <span class="mls-snapshot-change" id="sjMlsV3ChangePricePerSqFt">—</span>
      </div>
    </div>

    <div class="mls-period-controls" aria-label="Select how the MLS data is grouped">
      <span class="mls-period-label">Display data by:</span>
      <button type="button" class="mls-period-btn active" data-sj-mls-resolution="yearly" aria-pressed="true">Yearly</button>
      <button type="button" class="mls-period-btn" data-sj-mls-resolution="quarterly" aria-pressed="false">Quarterly</button>
      <button type="button" class="mls-period-btn" data-sj-mls-resolution="monthly" aria-pressed="false">Monthly</button>
    </div>

    <div class="mls-chart-grid">
      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Median Days on Market</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3DaysOnMarket" role="img" aria-label="{city} days on market chart with yearly, quarterly, and monthly views"></canvas></div>
      </article>

      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Sale-to-List Performance</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3SaleToList" role="img" aria-label="{city} sale-to-list performance chart with yearly, quarterly, and monthly views"></canvas></div>
      </article>

      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Median Sale Price</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3SalePrice" role="img" aria-label="{city} sale price chart with yearly, quarterly, and monthly views"></canvas></div>
      </article>

      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Year-over-Year Median Sale Price Change</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3SalePriceChange" role="img" aria-label="{city} year-over-year sale price change with yearly, quarterly, and monthly views"></canvas></div>
      </article>

      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Closed-Sales Volume</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3ClosedSales" role="img" aria-label="{city} closed-sales volume chart with yearly, quarterly, and monthly views"></canvas></div>
      </article>

      <article class="mls-chart-card">
        <h3 class="mls-chart-title">Price per Square Foot</h3>
        <div class="mls-chart-wrap"><canvas id="sjMlsV3PricePerSqFt" role="img" aria-label="{city} price per square foot chart with yearly, quarterly, and monthly views"></canvas></div>
      </article>
    </div>

    <p class="mls-dashboard-source">
      Source: locally stored MLS data for single-family homes, {first_month} through {latest_month}.
      An asterisk and gold marker identify an incomplete current period.
    </p>
  </div>
</section>"""


def display_month(label: str) -> str:
    try:
        return datetime.strptime(label, "%Y-%m").strftime("%B %Y")
    except ValueError as exc:
        raise ValueError(f"Invalid MLS coverage month: {label}") from exc


def asset_coverage(slug: str) -> tuple[str, str]:
    """Read the exact page coverage from the generated city data asset."""
    path = MLS_ASSET_DIR / f"{slug}.js"
    if not path.exists():
        raise FileNotFoundError(
            f"Generated MLS asset is missing: {path}. Run the data builder first."
        )
    text = path.read_text(encoding="utf-8")
    marker = "window.SAN_JOSE_MLS_V3_DATA="
    if marker not in text:
        raise ValueError(f"Unexpected MLS asset format: {path}")
    payload_text = text.split(marker, 1)[1].strip()
    if not payload_text.endswith(";"):
        raise ValueError(f"Unexpected MLS asset terminator: {path}")
    payload = json.loads(payload_text[:-1])
    metadata = payload.get("metadata", {})
    first = metadata.get("firstMonth")
    latest = metadata.get("latestMonth")
    if not isinstance(first, str) or not isinstance(latest, str):
        raise ValueError(f"MLS coverage metadata is missing: {path}")
    return display_month(first), display_month(latest)


def read_exact(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_exact(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def section_end(html: str, start: int) -> int:
    depth = 0
    for match in re.finditer(r"<section\b|</section\s*>", html[start:], re.I):
        token = match.group(0).lower()
        depth += -1 if token.startswith("</") else 1
        if depth == 0:
            return start + match.end()
    raise ValueError("Could not find matching </section>")


def replace_or_insert_mls_section(
    html: str,
    city: str,
    newline: str,
    first_month: str,
    latest_month: str,
) -> str:
    markup = section_markup(city, first_month, latest_month).replace("\n", newline)
    existing = html.find('<section class="sj-mls-dashboard"')
    if existing >= 0:
        end = section_end(html, existing)
        existing_markup = html[existing:end]
        source_match = re.search(
            r"Source: locally stored MLS data for single-family homes, "
            r"([A-Z][a-z]+ \d{4}) through ([A-Z][a-z]+ \d{4})\.",
            existing_markup,
        )
        if not source_match:
            raise ValueError(
                f"Protected MLS source sentence is unexpected for {city}; "
                "review the copy before updating."
            )
        expected_existing = section_markup(
            city, source_match.group(1), source_match.group(2)
        ).replace("\n", newline)
        if existing_markup != expected_existing:
            raise ValueError(
                f"Protected MLS section copy differs from the approved template "
                f"for {city}; do not overwrite it during a data update."
            )
        return html[:existing] + markup + html[end:]

    stats_start = html.find('<section class="sf-stats-section"')
    if stats_start < 0:
        raise ValueError("Zillow statistics section not found")
    insert_at = section_end(html, stats_start)
    comment = SECTION_COMMENT.replace("\n", newline)
    return html[:insert_at] + newline * 3 + comment + newline + markup + html[insert_at:]


def update_page(
    path: Path,
    city: dict,
    write: bool,
    first_month: str,
    latest_month: str,
    install_new: bool = False,
) -> bool:
    original = read_exact(path)
    newline = "\r\n" if "\r\n" in original else "\n"
    html = original
    existing_section = '<section class="sj-mls-dashboard"' in html

    new_heading = f"<h2>{city['name']} Trends from Zillow</h2>"
    new_chart_title = '<h3 class="chart-bare-title">Price Index (Zillow)</h3>'
    expected_scripts = SCRIPT_TEMPLATE.format(slug=city["slug"]).replace(
        "\n", newline
    )

    if existing_section:
        # Routine refreshes are date-only HTML updates. Every other owned
        # marker must already be exact; do not repair or rewrite it silently.
        if html.count(new_heading) != 1:
            raise ValueError(f"Protected Zillow heading is unexpected in {path.name}")
        if html.count(new_chart_title) != 1:
            raise ValueError(f"Protected Zillow chart title is unexpected in {path.name}")
        if html.count(CSS_LINK) != 1:
            raise ValueError(f"MLS stylesheet marker is unexpected in {path.name}")
        if html.count(expected_scripts) != 1:
            raise ValueError(f"MLS script block is unexpected in {path.name}")
        if "SAN JOSE MLS SAMPLE" in html:
            raise ValueError(f"Legacy MLS sample marker remains in {path.name}")

        html = replace_or_insert_mls_section(
            html, city["name"], newline, first_month, latest_month
        )
        changed = html != original
        if changed and write:
            write_exact(path, html)
        return changed

    if not install_new:
        raise InstallationRequired(
            f"{path.name} is newly MLS-eligible; rerun only after review with "
            "--install-new-pages"
        )

    # Explicit first-time installation is the only mode allowed to add the
    # dashboard or make the two owner-approved Zillow title changes.
    html = re.sub(
        r"\s*/\* =====================================================\s+"
        r"SAN JOSE MLS SAMPLE DASHBOARD V3.*?"
        r"/\* END SAN JOSE MLS SAMPLE DASHBOARD \*/\s*",
        newline,
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r"\s*<!-- =====================================================\s+"
        r"SAN JOSE MLS SAMPLE DASHBOARD V3.*?-->\s*",
        newline * 2,
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace("<!-- END SAN JOSE MLS SAMPLE DASHBOARD -->", "")

    old_heading = f"<h2>{city['name']} Real Estate Trends</h2>"
    if old_heading in html:
        html = html.replace(old_heading, new_heading, 1)
    elif new_heading not in html:
        legacy_headings = re.findall(r"<h2>[^<]+ Real Estate Trends</h2>", html)
        if len(legacy_headings) != 1:
            raise ValueError(f"Unexpected Zillow heading in {path.name}")
        html = html.replace(legacy_headings[0], new_heading, 1)

    old_chart_title = '<h3 class="chart-bare-title">Price Index (Historical)</h3>'
    if old_chart_title in html:
        html = html.replace(old_chart_title, new_chart_title, 1)
    elif new_chart_title not in html:
        raise ValueError(f"Unexpected Zillow chart title in {path.name}")

    if CSS_LINK not in html:
        html = html.replace("</head>", CSS_LINK + newline + "</head>", 1)

    html = replace_or_insert_mls_section(
        html, city["name"], newline, first_month, latest_month
    )

    old_script_block = re.compile(
        r"\s*<!-- SAN JOSE MLS SAMPLE CHARTS -->.*?"
        r"<!-- END SAN JOSE MLS SAMPLE CHARTS -->\s*",
        re.S,
    )
    html = old_script_block.sub(newline * 2, html, count=1)

    generic_script_block = re.compile(
        r"\s*<!-- CITY MLS CHARTS -->.*?<!-- END CITY MLS CHARTS -->\s*",
        re.S,
    )
    html = generic_script_block.sub(newline * 2, html, count=1)
    marker = "<!-- Default Statcounter code -->"
    if marker not in html:
        raise ValueError(f"Statcounter insertion marker missing in {path.name}")
    html = html.replace(marker, expected_scripts + newline * 2 + marker, 1)

    if html.count('<section class="sj-mls-dashboard"') != 1:
        raise ValueError(f"MLS section count is not one in {path.name}")
    if html.count("assets/js/san-jose-mls-v3-charts.js") != 1:
        raise ValueError(f"MLS chart script count is not one in {path.name}")

    changed = html != original
    if changed and write:
        write_exact(path, html)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--minimum-months", type=int, default=120)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--install-new-pages",
        action="store_true",
        help=(
            "Explicitly install the approved MLS section and title changes on "
            "newly eligible pages. Never use for a routine data refresh."
        ),
    )
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    eligible = {
        item["city"] for item in summary["available"]
        if item["single_family_months"] >= args.minimum_months
    }
    cities = [city for city in config["cities"] if city["name"] in eligible]

    changed = []
    installation_required = []
    for city in cities:
        path = REPO_ROOT / city["page"]
        first_month, latest_month = asset_coverage(city["slug"])
        try:
            if update_page(
                path,
                city,
                args.write,
                first_month,
                latest_month,
                install_new=args.install_new_pages,
            ):
                changed.append(path.name)
        except InstallationRequired:
            installation_required.append(path.name)

    mode = "Updated" if args.write else "Would update"
    print(f"{mode} {len(changed)} of {len(cities)} eligible pages.")
    for name in changed:
        print(f"- {name}")
    if installation_required:
        print("Newly eligible pages requiring explicit installation:")
        for name in installation_required:
            print(f"- {name}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
