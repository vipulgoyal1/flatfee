# Website data update order

Zillow and MLS are independent sources and must be refreshed as two separate
steps. Run them in this order so their diffs can be reviewed independently:

1. Complete the [Zillow update](zillow/FUTURE-UPDATES.md), including its final
   no-change checks.
2. Review and preferably commit the Zillow-only diff.
3. Complete the [MLS update](mls/FUTURE-UPDATES.md), including its final
   no-change checks.
4. Review and commit the MLS-only diff, then publish normally.

The Zillow updater owns Zillow values, Zillow chart/table assets,
neighborhood-ranking data, rankings pages, and `CMA.html`. The MLS updater owns
only the MLS dashboard, its generated city data assets, its CSS/script includes,
and the two approved Zillow titles used on an MLS-enabled page. The Zillow copy
validator deliberately ignores the exact MLS-owned section and includes, while
the MLS updater independently protects the MLS section copy.

Do not run both write steps before reviewing the first diff. Never use a generic
HTML formatter, whole-page generator, or global search-and-replace as part of a
data refresh.

A routine refresh is data-and-date only. It stops instead of deleting a Zillow
neighborhood section or installing a newly eligible MLS section. Those are
structural changes and require a separate owner-reviewed action.
