# Future MLS updates for city pages

Use this workflow after MLSListings/Aculist publishes a new month. It attempts
all 43 configured cities, builds assets only for cities with at least 120
single-family monthly observations, and leaves every other city page unchanged.

This workflow uses the local Windows folder below. It does not use a Google
Drive connector or browser automation:

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
  after it is reviewed and explicitly added to `KNOWN_ANOMALIES` in
  `scripts/build_city_mls_data.py`.

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

## Complete update procedure

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

The old manually collected files under `MLS Data\Cities` are not the source for
this workflow. They may contain different definitions, incomplete coverage, or
bad historical values and must not be used as an automatic fallback.
