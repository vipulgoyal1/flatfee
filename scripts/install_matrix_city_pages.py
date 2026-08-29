#!/usr/bin/env python3
"""Install or refresh the approved dashboard on active Matrix city pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_matrix_city_mls_data import TARGET_SLUGS
from update_aculist_city_pages import asset_coverage, update_page


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "city-pages.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cities = [city for city in config["cities"] if city["slug"] in TARGET_SLUGS]
    changed = []
    for city in cities:
        first, latest = asset_coverage(city["slug"])
        path = REPO_ROOT / city["page"]
        if update_page(
            path, city, args.write, first, latest, install_new=True
        ):
            changed.append(path.name)

    verb = "Updated" if args.write else "Would update"
    print(f"{verb} {len(changed)} of {len(cities)} Matrix city pages.")
    for name in changed:
        print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
