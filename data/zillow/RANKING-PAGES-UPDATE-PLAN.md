# Zillow ranking-page update plan

This plan covers the four interactive ranking pages and their hub:

- `Bay-Area-City-Appreciation-Ranking.html`
- `Southern-CA-City-Appreciation-Ranking.html`
- `US-City-Appreciation-Ranking.html`
- `US-Neighborhood-Appreciation-Ranking.html`
- `Appreciation-Rankings-Hub.html`

`Bay-Area-Price-Drop.html` is a dated editorial article, not a generated
ranking table. Keep it outside this automated update and review its claims in a
separate editorial task.

## Current-state findings

- The Bay Area and Southern California pages each contain 50 hard-coded city
  records and their own duplicated table-rendering code.
- The U.S. city asset contains 16,968 records grouped into 927 metro areas.
- The U.S. neighborhood asset contains 20,788 records grouped into 940 cities.
- The two national assets do not carry a source date, source definition,
  generation timestamp, or schema version.
- The pages label the latest ZHVI value as `Price Index`; it should be
  `Typical Home Value`.
- The California pages say the cities are ranked by population, but the data
  and displayed rank are based on the existing Zillow-derived order. Do not
  make a population claim unless a separate population source is added.
- The hub date is hard-coded as January 1, 2026. Its Rankings button links to
  the nonexistent `Appreciation-Rankings-Hub-v2.html`.
- The hub currently lists 32 city-level neighborhood pages. The current data
  supports 34; Concord and Milpitas are missing from the hub.
- The existing neighborhood asset contains at least one text-encoding defect
  (`Sierra Monta+¦a`).

## Data contract

Use only the two Zillow ZHVI sources already managed by the city-page pipeline:

- City single-family ZHVI, smoothed and seasonally adjusted.
- Neighborhood single-family ZHVI, smoothed and seasonally adjusted.

The current local files contain nationwide data through July 31, 2026. The
median-sale-price and days-to-pending sources are not needed for appreciation
rankings.

For every record, retain Zillow `RegionID` as the identity key and retain
Zillow `SizeRank` as source metadata. Calculate 1-, 3-, 5-, 10-, 20-, and
25-year total return and CAGR from the same calendar month. Use the newest date
shared by the city and neighborhood sources, and show unavailable history as an
em dash rather than inventing or carrying forward a value.

## Recommended implementation

### 1. Make ranking membership explicit

Add `config/ranking-pages.json` with the page name, geography rule, record
limit, sort default, and display labels for each ranking page.

- Preserve the current Bay Area and Southern California membership during the
  first refresh by recording the existing 50-city lists in configuration.
- Treat the displayed 1-50 number as the page's list order, not population
  rank. Label Zillow's actual `SizeRank` accurately if it is displayed.
- If the regional definitions are changed later, define them with an explicit
  county allowlist and then select the 50 lowest Zillow `SizeRank` values.
- Do not silently infer a new definition of “Bay Area” or “Southern
  California” during a monthly refresh.

### 2. Extend the Zillow build pipeline

Add a ranking-data build stage that reads the full nationwide city and
neighborhood CSVs already downloaded by `scripts/zillow_pipeline.py`. It should
not scrape Zillow pages and should not require a second download.

The builder should:

1. Validate source headers, identity fields, encoding, and the shared latest
   ZHVI date.
2. Recompute all return periods from the complete current source history.
3. Generate compact regional and national assets.
4. Write a manifest with schema version, source URLs, hashes, row counts,
   metric definition, and source date.
5. Fail before writing website files when required data or configuration is
   invalid.

Recommended outputs:

- `assets/data/rankings/bay-area-cities.js`
- `assets/data/rankings/southern-california-cities.js`
- `assets/data/rankings/us-cities.js`
- `assets/data/rankings/us-neighborhoods.js`
- `data/zillow/processed/ranking-pages-manifest.json`

### 3. Use one rendering system

Move sorting, null handling, number formatting, return/CAGR display, accessible
headers, and responsive table behavior into one shared script such as
`assets/js/ranking-table.js`.

Keep the geography-filter code as small page-specific adapters:

- U.S. cities: state, county, and metro filters plus result limit.
- U.S. neighborhoods: state and city filters.
- Regional pages: fixed configured subset with no separate inline dataset.

Remove the two hard-coded `rawData` arrays and the duplicated render functions
from the California HTML pages.

### 4. Normalize the page copy and labels

All four pages should use the same definitions and source note:

- `Typical Home Value`, not `Price Index`.
- `Total return` and `annualized return (CAGR)` defined once in plain language.
- `Single-family ZHVI, smoothed and seasonally adjusted` stated explicitly.
- `Data through July 2026` generated from the manifest, never typed by hand.
- `Data provided by Zillow Group` with a link to Zillow Research data.

Do not describe Zillow `SizeRank` as population rank. If a true population
ranking is desired, add and document a separate Census population dataset.

### 5. Generate the hub from current availability

Update the hub date and featured links from the same manifest. Generate the
city cards from `data/zillow/processed/city-pages.json` and include only cities
whose `neighborhoods` array is nonempty. This will add Concord and Milpitas
now, and it will automatically omit any city that loses qualifying
neighborhood data in a future refresh.

Correct the missing `Appreciation-Rankings-Hub-v2.html` link and the footer item
that incorrectly labels the U.S. city page as “California Appreciation
Rankings.”

### 6. Add check/write commands and future instructions

Create `scripts/update_ranking_pages.py` with the same safety pattern as the
city updater:

```powershell
python scripts/update_ranking_pages.py --check
python scripts/update_ranking_pages.py --write
python scripts/update_ranking_pages.py --check
```

The first command reports proposed assets and HTML changes; `--write` applies
them; the final check must report no stale generated content. Add these steps,
the page contract, and the regional membership policy to
`data/zillow/FUTURE-UPDATES.md` only when the ranking updater is implemented.

## Validation and review gates

Automated checks should require:

- One shared as-of month across all four rankings and the hub.
- Unique `RegionID` values, valid geography fields, and deterministic ordering.
- Recomputed total returns and CAGR matching independent test calculations.
- Configured 50-city regional membership with no additions or removals unless
  the configuration changes deliberately.
- Missing historical periods rendered as an em dash and sorted after values.
- No malformed Unicode, broken internal links, stale source dates, or old
  inline ranking datasets.
- Working state/county/metro/city filters and JavaScript syntax checks.
- An idempotent final `--check` and a clean `git diff --check`.

Before publishing, generate an old-versus-new audit. Flag for manual review:

- Typical home value changes greater than 15% since the prior data month.
- One-year return changes greater than 10 percentage points.
- Regional rank movements greater than 15 places.
- National group or row-count changes greater than 5%.
- Any one-year return outside plus or minus 50%, nonpositive home value,
  duplicate identity, or unexpected regional membership change.

These thresholds are review flags, not automatic rejection rules; Zillow can
revise history and geography coverage.

## Suggested execution order

1. Add the ranking configuration, builder, manifest, and tests without changing
   HTML.
2. Review the generated July 2026 datasets and the anomaly report.
3. Add the shared renderer and page-specific filters.
4. Update the four ranking pages and the hub in one coordinated write.
5. Run all city-page and ranking-page tests together, review the diff, and only
   then deploy through the normal website release process.
