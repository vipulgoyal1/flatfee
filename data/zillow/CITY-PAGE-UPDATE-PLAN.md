# Protected-copy update plan for all 43 city pages

Status: implemented. Zillow numbers and data assets can be refreshed without
rewriting the owner's page copy. See `FUTURE-UPDATES.md` for the recurring
procedure.

## Page contract

- Preserve every existing heading, label, paragraph, link, FAQ, service block,
  navigation item, and footer exactly unless the owner approves a specific
  wording change.
- A normal refresh may update only numeric stat values, chart/table data, and
  the numeric count of displayed neighborhoods.
- Preserve the approved neighborhood names and order. Newly available Zillow
  rows are reported but not silently added.
- If an approved neighborhood row is no longer available from Zillow, omit the
  data row and report it for review.
- If a city has no approved, qualifying neighborhood rows, omit the entire
  Neighborhood Ranking section. Do not show an unavailable message.
- Adding a new Neighborhood Ranking section requires approval because it also
  requires new visible copy.

The approved copy and membership snapshot is
`config/city-page-copy-contract.json`. The updater validates protected-copy
hashes before writing. A wording change therefore stops the update instead of
being overwritten or silently adopted.

## Numerical data contract

- Price changes and charts: City single-family ZHVI, smoothed and seasonally
  adjusted.
- Median sale price: City single-family, smoothed and seasonally adjusted.
- The value displayed under the existing `Median Days on Market` label comes
  from Zillow's all-homes median-days-to-pending series. Correcting that label
  requires owner approval.
- Neighborhood values and returns: Neighborhood single-family ZHVI, using
  current and same-month historical values.
- Rebuild the complete history every time because Zillow may revise earlier
  values.

## Update sequence

1. Download and validate all configured Zillow sources.
2. Build `data/zillow/processed/city-pages.json` for all 43 cities.
3. Run the page updater in check mode. Review source dates, missing approved
   rows, and new Zillow rows that will not be added.
4. Apply the update only when the proposed HTML changes are limited to numbers,
   data includes, and approved section omissions.
5. Run the updater again; it must report no stale pages or assets.
6. Run regression, JavaScript syntax, and diff checks before publishing.

## Required verification

- Exactly 43 configured pages and 43 complete city records.
- All protected-copy hashes match the approved contract.
- All six existing stat tiles keep their original labels and order.
- Chart and table data use the current source files.
- Existing neighborhood membership and display names remain unchanged unless
  explicitly approved.
- Pages without a neighborhood section contain neither a ranking marker nor an
  unavailable message.
- No headings, labels, descriptions, links, FAQs, service copy, navigation, or
  footer text changes in the update diff.
- San Jose's ranking paragraph and Rankings Hub sentence receive an explicit
  regression check.

Any proposed accuracy or terminology improvement must be given to the owner as
a separate approve-or-deny list. Do not bundle copy changes into a data refresh.
