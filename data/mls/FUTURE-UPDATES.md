# Future MLS updates for city pages

City MLS charts currently use two reviewed source routes. Use Aculist for the
cities its API covers and the dated 22-city MLSListings Matrix archive for the
20 active cities listed in `scripts/build_matrix_city_mls_data.py`. Santa
Barbara and Santa Clarita are intentionally excluded because their Matrix data
was too sparse or unreliable for a citywide dashboard. Both active routes write
the same generated asset format and use the same protected San Jose template.

All source files are stored in the local Windows folder below. Do not use a
Google Drive connector. Matrix exports are downloaded through the signed-in
Chrome session as described below; all build and page-update steps are local:

`C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data`

If Zillow and MLS are both being refreshed, follow the combined order in
[Website data update order](../WEBSITE-DATA-UPDATES.md): Zillow first, MLS
second. The two workflows use different generated assets and copy boundaries.

## Copy-preservation rules

- A routine MLS refresh may update generated numerical assets, the latest-data
  fallback tile date, and the first/latest months in the MLS source sentence.
  It may not rewrite any other visible text.
- An existing MLS section must exactly match the approved San Jose template,
  apart from the city name and coverage months. The updater stops if its text or
  structure differs; it does not silently overwrite the difference.
- A routine update never installs an MLS section on a newly eligible city. It
  stops and lists that page. A separate, explicit first-time installation may
  add the approved MLS section, CSS link, and script tags, and may make only
  these two previously approved title changes:

  - `<City> Real Estate Trends` to `<City> Trends from Zillow`
  - `Price Index (Historical)` to `Price Index (Zillow)`

- Do not use an HTML parser/serializer, formatter, whole-page template, or
  global search-and-replace. Do not edit headings, paragraphs, links, FAQs,
  neighborhood copy, service copy, navigation, or footer text.
- If any visible wording should change, list the exact old and proposed text
  for owner approval. After approval, update the MLS template deliberately. If
  non-MLS copy or either approved Zillow title also changes, recapture the
  city-page copy contract. Never bundle a wording change into a normal data
  refresh.
- If a city is unavailable or has fewer than 120 months, do not add, remove, or
  alter its MLS section and do not show an unavailable message. Report it for
  review.
- Never fill a missing value with an estimate or silently substitute the older
  `MLS Data\Cities` spreadsheets. A source anomaly may be set to null only
  after it is reviewed and explicitly added to `KNOWN_ANOMALIES` in the
  applicable Aculist or Matrix asset builder.

## Data definitions

The download script queries the official MLSListings/Aculist market-trends API
for monthly `Residential - Single Family` rows and filters each city to its
configured county. The five downloaded metrics are:

- Median sale price: `MedSalePrice`
- Median days on market: `SoldMedDOM`
- Sale-to-list performance: `AvgSaleOverListPrice`, displayed as a percentage
- Closed-sales volume: `SoldCount`
- Price per square foot: `AvgSalePricePerSqft`

Aculist timestamps a reported month on the first day of the following month.
The downloader subtracts one day so, for example, a source date of August 1 is
displayed as July. The charts contain no seasonal adjustment and no moving
average. Closed sales are summed in quarterly and yearly views; the other four
metrics average the reported monthly values. The year-over-year sale-price
chart is derived from median sale price.

## MLSListings Matrix workflow for the 20 active additional cities

Download and archive all 22 Matrix cities even though only 20 currently have
published MLS dashboards:

- Anaheim
- Bakersfield
- Chula Vista
- Elk Grove
- Fresno
- Glendale
- Huntington Beach
- Irvine
- Long Beach
- Los Angeles
- Modesto
- Pasadena
- Riverside
- Roseville
- Sacramento
- San Diego
- San Luis Obispo
- Santa Ana
- Santa Barbara (archive only; do not publish)
- Santa Clarita (archive only; do not publish)
- Stockton
- Ventura

Use the saved MLSListings username and password in the signed-in Chrome
profile. This is an MLSListings login, not a Google login. In the saved Matrix
market-statistics report, select one city at a time, `Residential / Single
Family`, monthly grouping, January 2002 through the latest complete reported
month, and export all ten tables. Put downloads in a staging folder where
Chrome can download automatically. Before starting, turn off Chrome's “ask
where to save each file” option for the session and allow multiple automatic
downloads from MLSListings. After each city, move and rename the ten files into
the dated city folder before starting the next city, so identical browser
filenames cannot overwrite one another or trigger repeated save prompts:

`MLS Data\Matrix-YYYY-MM-DD-22-cities\<City>\`

Each city folder must contain these exact filenames:

- `01 Active Listings - Dollar Volume + Number.csv`
- `02 Contingent Pending - Dollar Volume + Number.csv`
- `03 Days to Sell - Average + Median.csv`
- `04 List Price - Average + Median.csv`
- `05 Original Price - Average + Median.csv`
- `06 Sale Price - Average + Median.csv`
- `07 Price Per SqFt + Months of Inventory.csv`
- `08 Sale to List + Sale to Original Price Ratios.csv`
- `09 Closed Sales - Dollar Volume + Number.csv`
- `10 New + Expired Listings - Number.csv`

The website builder uses the median columns in files 03 and 06, the
price-per-square-foot value in file 07, sale-to-list ratio in file 08, and
number of sales in file 09. The other exports are retained as source evidence
and for future chart work. Never use average as a replacement for a missing
median.

Every current archive file contains rows beginning in January 2002, but older
rows must not be equated with usable data. A review of the current archive found
broadly usable pre-2016 coverage across all five published metrics for Elk
Grove, Fresno, Los Angeles, Modesto, Roseville, Sacramento, and Stockton. The
other 15 cities have incomplete or implausible pre-2016 coverage—most often in
days on market—and must remain at their approved website start dates unless a
separate audit approves a metric-specific earlier start. Raw pre-2016 rows are
retained for source evidence and future review; the builder must not publish
them merely because they are nonblank.

Build and validate the assets before changing HTML. Always pass the new dated
source path explicitly; the script infers the latest common month and stops if
any required city or metric has different coverage:

```powershell
$matrixDir = Join-Path $mlsStore "Matrix-$runDate-22-cities"
python scripts\build_matrix_city_mls_data.py --source $matrixDir
python scripts\build_matrix_city_mls_data.py --source $matrixDir --write
```

Review every validation failure against the raw CSV. Genuine isolated source
errors may be represented only as `null` entries added deliberately to
`KNOWN_ANOMALIES`; never interpolate them. Keep the approved shorter starts for
Bakersfield and San Diego unless a new source review proves the older coverage
reliable. Do not restore Santa Barbara or Santa Clarita to `TARGET_SLUGS` or
their HTML pages without a separate source-quality review and owner approval.

The approved exclusions are persistent builder rules, not one-time edits to a
generated asset. Los Angeles days-on-market begins in January 2020 through
`SERIES_START_MONTHS`; its other charts retain January 2016 history. The
reviewed isolated bad cells for Bakersfield, Fresno, Sacramento, and Stockton
remain in `KNOWN_ANOMALIES` and are emitted as gaps on every rebuild. Do not
remove either rule merely because a later download contains the same bad
historical values.

The builder also stops on new obvious display errors: zero median days on
market with at least 20 closed sales, a price-per-square-foot value at least
50% away from its nearby median, or a sale-to-list value at least 12 percentage
points away from its nearby median. These checks are review gates, not automatic
deletion rules. Confirm a flagged value in the raw CSV before adding it to
`KNOWN_ANOMALIES`.

Then preview and apply the date-only HTML refresh:

```powershell
python scripts\install_matrix_city_pages.py
python scripts\install_matrix_city_pages.py --write
python scripts\install_matrix_city_pages.py
```

Because these 20 pages are installed, the first command should normally
list only pages whose two coverage dates need updating, and the final command
must report `Would update 0`. The updater verifies the complete MLS template,
Zillow titles, stylesheet, and script block before changing only the coverage
dates. It stops rather than repairing altered copy. Do not recapture the copy
contract for a routine data update.

## Aculist complete update procedure

Run these commands from the repository root in PowerShell. Always pass the
dated paths explicitly; do not rely on the example date embedded in a script's
default.

1. Start from a reviewed worktree and create a new dated download directory:

   ```powershell
   git status --short
   $runDate = Get-Date -Format 'yyyy-MM-dd'
   $mlsStore = 'C:\Users\vipul\My Drive (info@goyalteam.com)\FFR\MLS Data'
   $downloadDir = Join-Path $mlsStore "Aculist Downloads\$runDate"
   $summaryFile = Join-Path $downloadDir 'download-summary.json'
   ```

   Existing unrelated changes must be understood before continuing. Prefer a
   separate Zillow commit before starting the MLS write steps.

2. Download all available configured cities into the new folder:

   ```powershell
   python scripts\download_aculist_city_data.py --output $downloadDir
   ```

   Review `$summaryFile`. Check `available`, `unavailable`,
   `single_family_months`, coverage dates, `validation_warnings`, and
   `validation_errors`. The command must finish without validation errors.
   Availability can change, so do not assume the previous city's list. A city
   becoming newly eligible is a structural installation, not a routine refresh.

3. Validate the website assets without writing:

   ```powershell
   python scripts\build_city_mls_data.py --check `
     --mls-root $downloadDir --summary $summaryFile --minimum-months 120
   ```

   Stop if metric coverage differs, a required file is missing, or a value is
   outside the configured safety range. Review any unusual jump against the raw
   API JSON before deciding whether it is genuine.

4. Write the generated numerical city assets:

   ```powershell
   python scripts\build_city_mls_data.py --write `
     --mls-root $downloadDir --summary $summaryFile --minimum-months 120
   ```

   This writes `assets/data/mls/<city-slug>.js`. It does not edit HTML.

5. Preview the HTML update. This command is read-only because `--write` is not
   supplied:

   ```powershell
   python scripts\update_aculist_city_pages.py `
     --summary $summaryFile --minimum-months 120
   ```

   For an already enabled city, the expected HTML change is normally only two
   date lines: the latest-data fallback tile and the MLS source sentence. New
   chart numbers belong in the generated JavaScript asset, not in paragraphs or
   headings. A protected-copy error means stop and review; do not recapture or
   bypass the contract merely to make the command pass. If the command lists a
   newly eligible page and exits 2, pause for a separate installation review.

6. Apply the HTML update, then immediately repeat the read-only check:

   ```powershell
   python scripts\update_aculist_city_pages.py `
     --summary $summaryFile --minimum-months 120 --write

   python scripts\update_aculist_city_pages.py `
     --summary $summaryFile --minimum-months 120
   ```

   The second command must report `Would update 0` for every eligible page.

### Explicit first-time installation exception

Installing an MLS dashboard is not a data-only refresh because it adds visible
copy and changes two titles. Do it only as a separately reviewed action:

```powershell
python scripts\update_aculist_city_pages.py `
  --summary $summaryFile --minimum-months 120 --install-new-pages

python scripts\update_aculist_city_pages.py `
  --summary $summaryFile --minimum-months 120 --install-new-pages --write
```

Review the complete HTML diff before writing and again afterward. Then recapture
the exact Zillow page-copy contract from the approved working tree and rerun
both updater checks:

```powershell
python scripts\capture_city_page_contract.py --working-tree
python scripts\update_city_pages.py --check
python scripts\update_aculist_city_pages.py --summary $summaryFile
```

Do not use `--install-new-pages` during a normal monthly update.

7. Confirm Zillow compatibility and run final checks:

   ```powershell
   python scripts\update_city_pages.py --check
   python -m py_compile scripts\download_aculist_city_data.py `
     scripts\build_city_mls_data.py scripts\update_aculist_city_pages.py
   node --check assets\js\san-jose-mls-v3-charts.js
   git diff --check
   git status --short
   ```

   The Zillow check must exit 0 with empty `changed_pages` and
   `changed_assets`. This proves that the MLS additions have not broken the
   Zillow copy contract.

8. Review the diff before committing:

   ```powershell
   git diff --stat
   git diff --word-diff=plain -- '*.html'
   git diff -- assets/data/mls assets/js/san-jose-mls-v3-charts.js `
     assets/css/city-mls-dashboard.css
   ```

   Search the HTML diff for changed headings, paragraphs, links, FAQ text,
   navigation, and footer text. Apart from an approved first-time installation,
   none may change. Spot-check San Jose and at least one other eligible city at
   yearly, quarterly, and monthly resolutions before publishing.

## Download contents and retention

Each available city receives `raw-api.json`, a normalized
`Single-Family-Monthly.csv`, and five metric CSVs. The dated directory also
contains `download-summary.json`. Keep the current download and the immediately
previous successful download until the website update is validated and
committed. Older raw download directories may then be removed under the site's
normal data-retention policy; never delete the generated website assets that
are being committed.

The old manually collected files under `MLS Data\Cities` are not a source for
either workflow. They may contain different definitions, incomplete coverage,
or bad historical values and must not be used as an automatic fallback. A
dated `Matrix-YYYY-MM-DD-22-cities` archive is a separate reviewed source and
must not be confused with that legacy folder.
