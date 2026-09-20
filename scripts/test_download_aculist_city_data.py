"""Reporting-month regressions: never label incomplete September as August."""
import unittest
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_aculist_city_data import display_month, completed_rows, latest_complete_month
from build_city_mls_data import KNOWN_ANOMALIES


class AculistReportingMonthTests(unittest.TestCase):
    def row(self, month, name):
        return {'Period': f'2026-{month:02}', 'DateValue': f'2026-{month:02}-01T00:00:00Z',
                'Year': 2026, 'QuarterMonth': name}

    def test_midnight_utc_does_not_shift_reporting_month(self):
        self.assertEqual(display_month(self.row(8, 'August')), '2026-08')
        self.assertEqual(display_month(self.row(1, 'January')), '2026-01')

    def test_partial_current_month_is_excluded(self):
        august, september = self.row(8, 'August'), self.row(9, 'September')
        self.assertEqual(completed_rows([august, september], '2026-08'), [august])
        self.assertEqual(latest_complete_month(date(2026, 9, 19)), '2026-08')
        self.assertEqual(latest_complete_month(date(2026, 1, 1)), '2025-12')

    def test_conflicting_month_fields_fail_closed(self):
        for patch in ({'Period': '2026-07'}, {'Year': 2025}, {'QuarterMonth': 'July'}):
            with self.assertRaises(ValueError):
                display_month({**self.row(8, 'August'), **patch})

    def test_exclusions_follow_the_same_source_cells(self):
        self.assertEqual(KNOWN_ANOMALIES['berkeley']['pricePerSqFt'], {'2019-08'})
        self.assertEqual(KNOWN_ANOMALIES['oakland']['pricePerSqFt'], {'2018-08', '2018-09', '2019-03'})
        self.assertEqual(KNOWN_ANOMALIES['san-francisco']['pricePerSqFt'], {'2017-06'})


if __name__ == '__main__':
    unittest.main()
