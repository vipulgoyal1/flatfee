"""Regression tests for MLS/Zillow ownership and protected MLS copy."""

from __future__ import annotations

import difflib
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from update_aculist_city_pages import (  # noqa: E402
    InstallationRequired,
    SECTION_COMMENT,
    SCRIPT_TEMPLATE,
    replace_or_insert_mls_section,
    section_markup,
    update_page,
)
from update_city_pages import normalize_page_copy  # noqa: E402


class AculistCityPageUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.section = section_markup(
            "San Jose", "January 2016", "July 2026"
        )

    def test_existing_section_update_changes_only_coverage_dates(self) -> None:
        updated = replace_or_insert_mls_section(
            self.section,
            "San Jose",
            "\n",
            "January 2016",
            "August 2026",
        )
        changes = [
            line
            for line in difflib.ndiff(
                self.section.splitlines(), updated.splitlines()
            )
            if line[:2] in {"- ", "+ "}
        ]
        self.assertEqual(
            changes,
            [
                '-         <strong class="mls-snapshot-value" '
                'id="sjMlsV3LatestMonth">July 2026</strong>',
                '+         <strong class="mls-snapshot-value" '
                'id="sjMlsV3LatestMonth">August 2026</strong>',
                "-       Source: locally stored MLS data for single-family homes, "
                "January 2016 through July 2026.",
                "+       Source: locally stored MLS data for single-family homes, "
                "January 2016 through August 2026.",
            ],
        )

    def test_existing_section_with_altered_copy_is_rejected(self) -> None:
        altered = self.section.replace(
            "Median Days on Market</h3>", "Typical Days to Sell</h3>", 1
        )
        with self.assertRaisesRegex(ValueError, "Protected MLS section copy differs"):
            replace_or_insert_mls_section(
                altered,
                "San Jose",
                "\n",
                "January 2016",
                "August 2026",
            )

    def test_zillow_copy_hash_ignores_only_approved_mls_owned_markup(self) -> None:
        base = """<main>
<h2>San Jose Trends from Zillow</h2>
<h3 class="chart-bare-title">Price Index (Zillow)</h3>
<p>Protected page copy.</p>
</main>
<!-- Default Statcounter code -->
"""
        mls_enabled = """<main>
<h2>San Jose Trends from Zillow</h2>
<h3 class="chart-bare-title">Price Index (Zillow)</h3>
<p>Protected page copy.</p>
</main>
<link rel="stylesheet" href="assets/css/city-mls-dashboard.css">
"""
        mls_enabled += SECTION_COMMENT + "\n" + self.section + "\n"
        mls_enabled += SCRIPT_TEMPLATE.format(slug="san-jose") + "\n"
        mls_enabled += "<!-- Default Statcounter code -->\n"
        self.assertEqual(
            normalize_page_copy(base), normalize_page_copy(mls_enabled)
        )

        changed_copy = mls_enabled.replace(
            "Protected page copy.", "Silently rewritten page copy."
        )
        self.assertNotEqual(
            normalize_page_copy(base), normalize_page_copy(changed_copy)
        )

        changed_title = mls_enabled.replace(
            "San Jose Trends from Zillow", "San Jose Real Estate Trends"
        )
        self.assertNotEqual(
            normalize_page_copy(base), normalize_page_copy(changed_title)
        )

    def test_new_page_installation_requires_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Example.html"
            path.write_text(
                "<html><body><h2>Example Real Estate Trends</h2></body></html>",
                encoding="utf-8",
            )
            with self.assertRaises(InstallationRequired):
                update_page(
                    path,
                    {"name": "Example", "slug": "example"},
                    False,
                    "January 2016",
                    "August 2026",
                )


if __name__ == "__main__":
    unittest.main()
