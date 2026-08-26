# Zillow city-page data and publishing pipeline

The data pipeline downloads the four Zillow Research datasets required by the
43 California city pages and produces one compact JSON file. A separate page
updater uses that file to generate the consistent market sections, chart data,
and neighborhood data for every page.

The four sources are:

- City single-family ZHVI, smoothed and seasonally adjusted.
- Neighborhood single-family ZHVI, smoothed and seasonally adjusted.
- City single-family median sale price, smoothed and seasonally adjusted.
- City all-homes median days to pending, smoothed monthly.

## Run

From the repository root:

```powershell
python scripts/zillow_pipeline.py all
```

Individual stages are also available:

```powershell
python scripts/zillow_pipeline.py download
python scripts/zillow_pipeline.py build
python scripts/zillow_pipeline.py validate
python -m unittest discover -s scripts -p "test_*.py"
```

The page updater is read-only unless `--write` is supplied:

```powershell
python scripts/update_city_pages.py --check
python scripts/update_city_pages.py --write
```

Raw CSV files and their download manifest are written to `data/zillow/raw/` and
are gitignored. The compact output is written to
`data/zillow/processed/city-pages.json`.

For the complete monthly procedure, review points, failure rules, and generated
file policy, see [FUTURE-UPDATES.md](FUTURE-UPDATES.md).

## Current metric policy

- City and neighborhood values use single-family ZHVI, smoothed and seasonally
  adjusted.
- The consistent four-tile market snapshot is 10-year price change, 25-year
  price change, single-family median sale price, and median days to pending.
- `Median days to pending` is used instead of the inaccurate `Median days on
  market` label. Zillow's metric stops when a listing becomes pending and does
  not include the pending-to-close period.
- Each metric uses the latest date with a value for all 43 cities. Metric dates
  are stored separately because median sale price is normally published later
  than ZHVI and days-to-pending data.
- Returns compare the latest value with the same month 1, 3, 5, 10, 20, and 25
  years earlier.
- Neighborhoods require both a current value and a 10-year comparison value.
- Raw source files are fully replaced on every run; the updater does not append
  only the latest month.
- The generated attribution is `Data provided by Zillow Group`.

Zillow's current download menu does not advertise the two City-level market
files, but their official `files.zillowstatic.com` CSV endpoints remain publicly
accessible. The pipeline health-checks their headers and contents on every run,
does not scrape Zillow city pages, and replaces an existing raw file only after
the new download passes validation.
