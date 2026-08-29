# Future Zillow updates for all website HTML pages

If MLS data is also being refreshed, finish this entire Zillow procedure first,
review its diff, and then follow
[the MLS procedure](../mls/FUTURE-UPDATES.md). The combined ownership and
ordering rules are summarized in
[Website data update order](../WEBSITE-DATA-UPDATES.md). The Zillow copy
validator ignores only the exact MLS-owned dashboard and includes; the MLS
updater protects that copy independently.

Run this workflow monthly, after Zillow publishes a new data month. It covers
all 43 city pages, all four appreciation-ranking pages, the appreciation
rankings hub, and `CMA.html` so dates, calculations, chart data, and ranking
values remain consistent across the website.

## What is generated

The numerical source of truth is `data/zillow/processed/city-pages.json`.
Approved visible copy, exact titles, and neighborhood membership are protected by
`config/city-page-copy-contract.json`. The page updater changes only:

- Numeric values inside the six existing market tiles.
- Historical chart data and approved neighborhood-table data.
- The numeric neighborhood count when Zillow drops an approved row.
- `assets/data/city-pages/<city-slug>.js` for chart and neighborhood rows.

The shared rendering code is `assets/js/city-page-data.js`, and the shared
styles are in `assets/theme/css/city-data.css`.

`CMA.html` uses `assets/data/ca_cities_zhvi_data.js`. Unlike the 43 city-page
assets, this file contains every California city in Zillow's city source so the
CMA city selector retains full statewide coverage. Generate it only with
`scripts/update_cma_data.py`; do not rebuild it from the 43-city page subset.

Do not silently rewrite headings, labels, descriptions, links, FAQs, service
copy, navigation, footers, or neighborhood names. If wording or neighborhood
membership should change, prepare a list for the owner and wait for approval.
After approval, edit the pages and deliberately recapture the copy contract.
An unapproved copy change must make the updater fail rather than overwrite it.

## Complete monthly update procedure for every data-driven HTML page

Run the commands from the repository root in PowerShell.

1. Download, build, and validate all four official Zillow datasets:

   ```powershell
   python scripts/zillow_pipeline.py all
   ```

   Do not continue if this reports a download, header, city-identity, coverage,
   or calculation error. The pipeline requires complete market data for all 43
   configured cities.

2. Preview which pages and data assets are stale:

   ```powershell
   python scripts/update_city_pages.py --check
   ```

   Exit code 1 is expected when new Zillow data is ready to apply. Review the
   JSON report: it must say `configured_pages: 43`. The
   `cities_with_neighborhood_sections` and
   `cities_without_neighborhood_sections` must sum to 43. New Zillow
   neighborhood rows are reported but are not added without approval. Exit
   code 2 means an error; do not write.

   Also preview the full California dataset used by `CMA.html`:

   ```powershell
   python scripts/update_cma_data.py --check
   ```

   Exit code 1 is expected after a new Zillow download. Confirm that the latest
   date matches the city ZHVI source and that California city coverage remains
   above the generator's safety threshold. Exit code 2 means an error; do not
   write.

3. Apply the coordinated update:

   ```powershell
   python scripts/update_city_pages.py --write
   python scripts/update_cma_data.py --write
   ```

   In `CMA.html`, the CMA generator changes only the dataset month in the two
   adjusted-result labels and the numeric cache version on
   `ca_cities_zhvi_data.js?v=YYYYMM`. The cache version prevents a browser from
   retaining the prior month's CMA data after deployment.

4. Preview and apply the appreciation-ranking update. The first check should
   exit 1 when a new Zillow month is available; review its exception and flag
   report before writing:

   ```powershell
   python scripts/update_ranking_pages.py --check
   python scripts/update_ranking_pages.py --write
   ```

5. Confirm that nothing generated remains stale and run all regression checks:

   ```powershell
   python scripts/update_city_pages.py --check
   python scripts/update_cma_data.py --check
   python scripts/update_ranking_pages.py --check
   python scripts/zillow_pipeline.py validate
   python -m unittest discover -s scripts -p "test_*.py" -v
   node --check assets/js/city-page-data.js
   node --check assets/data/us_metro_city_data.js
   node --check assets/data/us_neighborhoods_data.js
   node --check assets/data/ca_cities_zhvi_data.js
   node --check assets/js/us_city_rankings_flexible.js
   git diff --check
   git status --short
   ```

   The second updater checks must exit 0. The city-page report must have empty
   `changed_pages` and `changed_assets` arrays, and the CMA report must say
   `asset_current: true` and `html_current: true`. All tests and syntax checks
   must pass.

6. Review the diff before publishing. At minimum, inspect San Francisco,
   Anaheim, Dublin, Los Angeles, and San Jose. Confirm that the updater changed
   only numbers/data and dates. No headings, labels, sections, paragraphs, or
   links may change. Confirm that omitted sections show no
   unavailable message. Review each metric's source month in the updater report;
   Zillow's median sale price file can lag the other sources. Also inspect the
   Bay Area, Southern California, U.S. city, and U.S. neighborhood rankings and
   confirm that the hub shows the shared Zillow data date.

7. Commit and deploy through the site's normal release process only after the
   review is complete. Downloading or running the updater does not deploy the
   website.

## Data and version-control policy

- Raw Zillow CSVs and their download manifest live in `data/zillow/raw/` and are
  intentionally gitignored.
- Commit `data/zillow/processed/city-pages.json`, the 43 generated city assets,
  `assets/data/ca_cities_zhvi_data.js`, and the coordinated numeric HTML
  changes.
- `config/city-page-copy-contract.json` is an approval boundary. Change it only
  after the owner approves the corresponding visible copy or membership change.
- Commit pipeline, configuration, shared JavaScript, or shared CSS changes only
  when the update logic itself changes.
- The pipeline fully replaces each raw source file; it never appends only the
  newest month or carries forward deleted neighborhood rows.
- Do not scrape Zillow city pages as a fallback. Resolve an official source-file
  failure or update `config/zillow-sources.json` only after verifying Zillow's
  current Research download definition.

## Metric definitions that must stay consistent

- Typical home value and historical returns: single-family ZHVI, smoothed and
  seasonally adjusted.
- Median sale price: single-family, smoothed and seasonally adjusted.
- Median days to pending: all homes, smoothed monthly. It ends when a listing
  becomes pending and excludes the pending-to-close period.
- Neighborhood tables: single-family ZHVI for the approved neighborhood list
  and order in the copy contract. Do not add newly available Zillow rows
  automatically. If an approved row disappears from Zillow, omit that data row
  and report it for review.
- Pages already approved without a neighborhood section remain without one. If
  an existing approved section loses all qualifying rows, the routine updater
  stops instead of deleting its visible copy. Removing that section requires
  an explicit owner-approved structural edit; do not display an empty-state or
  unavailable message.

If a requested definition changes, update the source configuration, pipeline,
tests, page generator, and this document together before regenerating pages.

`scripts/capture_city_page_contract.py` is not part of the monthly workflow.
Use it only from a revision containing owner-approved copy, then review the
contract diff before committing it.

## Appreciation-ranking pages

The four appreciation-ranking pages use the same city and neighborhood ZHVI
downloads as the city pages. Their normal refresh changes only prices, returns,
CAGR values, Zillow size-rank numbers, and generated numeric data. Do not edit
headings, descriptions, labels, links, filters, geography names, or existing
record membership during a numerical refresh.

After completing the Zillow download, preview and apply a ranking refresh with:

```powershell
python scripts/update_ranking_pages.py --check
python scripts/update_ranking_pages.py --write
python scripts/update_ranking_pages.py --check
python -m unittest scripts.test_update_ranking_pages -v
git diff --check
```

The final check must exit 0 with an empty `changed_files` list. Review the
reported `review_flags` and `unavailable_legacy_records` before publishing.
The updater must stop if a configured regional city, the default top U.S. city
set, or the default San Jose neighborhood ranking cannot be matched. Smaller
legacy records that Zillow no longer supplies keep their names but receive
null numerical values, which the pages render as unavailable; stale values are
never carried forward. Duplicate neighborhood names are matched by their prior
Zillow size rank without changing the displayed name.

All return periods use the latest shared source month. For example, a July 2026
refresh compares July 2026 with July 2025, July 2023, July 2021, July 2016,
July 2006, and July 2001. Missing historical values remain null. The generated
source hashes, coverage counts, and match exceptions are recorded in
`data/zillow/processed/ranking-pages-manifest.json`.
