from pathlib import Path
import argparse
import time
import xml.etree.ElementTree as ET

import requests
from tqdm import tqdm


# ============================================================
# CONFIG
# ============================================================

OUTPUT_ROOT = Path("data/raw/clerk_xml")

# Default to the current 119th Congress when no years are
# supplied on the command line.
DEFAULT_YEARS = [2025, 2026]

# Roll calls start at 1 each calendar year/session.
START_ROLL = 1

# Safety ceiling. House sessions will normally end well before this.
MAX_ROLL = 1000

# Once we've reached the current end of a year's roll calls,
# stop after this many consecutive missing rolls.
CONSECUTIVE_MISSING_LIMIT = 5

# Be polite to the Clerk server.
REQUEST_DELAY_SECONDS = 0.10

REQUEST_TIMEOUT_SECONDS = 30

BASE_URL = "https://clerk.house.gov/evs/{year}/roll{roll:03d}.xml"


# ============================================================
# HELPERS
# ============================================================

def roll_path(year, roll):
    """Return the local path for one raw Clerk XML roll call."""
    return OUTPUT_ROOT / str(year) / f"roll{roll:03d}.xml"


def roll_url(year, roll):
    """Return the Clerk XML URL for one roll call."""
    return BASE_URL.format(year=year, roll=roll)


def is_valid_rollcall_xml(content):
    """
    Verify that downloaded content is actually a Clerk roll-call XML file.

    We require:
      - valid XML
      - root tag = rollcall-vote
      - vote-metadata exists
      - vote-data exists
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return False

    if root.tag != "rollcall-vote":
        return False

    if root.find("vote-metadata") is None:
        return False

    if root.find("vote-data") is None:
        return False

    return True


def existing_roll_numbers(year):
    """Return the set of valid-looking roll numbers already saved locally."""
    year_dir = OUTPUT_ROOT / str(year)

    if not year_dir.exists():
        return set()

    rolls = set()

    for path in year_dir.glob("roll*.xml"):
        number = path.stem.removeprefix("roll")

        if number.isdigit():
            rolls.add(int(number))

    return rolls


def find_first_missing_roll(year):
    """
    Find the first missing roll in the local sequence.

    Example:
      existing = 1, 2, 3, 4, 6
      result   = 5

    If 1 through 314 exist, result = 315.
    """
    existing = existing_roll_numbers(year)

    roll = START_ROLL

    while roll in existing:
        roll += 1

    return roll


def save_xml_atomic(content, destination):
    """
    Save via a temporary file and then replace the destination.

    This avoids leaving a partial XML file if writing is interrupted.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path = destination.with_suffix(".xml.tmp")
    temp_path.write_bytes(content)
    temp_path.replace(destination)


def download_one(session, year, roll):
    """
    Attempt to download one Clerk roll call.

    Returns:
      "downloaded"
      "missing"
      "invalid"
      "error"
    """
    url = roll_url(year, roll)
    destination = roll_path(year, roll)

    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"\nRequest error for {year} roll {roll}: {exc}")
        return "error"

    if response.status_code == 404:
        return "missing"

    if response.status_code != 200:
        print(
            f"\nUnexpected HTTP {response.status_code} "
            f"for {year} roll {roll}: {url}"
        )
        return "error"

    if not is_valid_rollcall_xml(response.content):
        print(
            f"\nInvalid XML response for {year} roll {roll}: {url}"
        )
        return "invalid"

    save_xml_atomic(response.content, destination)

    return "downloaded"


# ============================================================
# YEAR DOWNLOADER
# ============================================================

def download_year(session, year):
    year_dir = OUTPUT_ROOT / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    existing_before = existing_roll_numbers(year)
    first_missing = find_first_missing_roll(year)

    print(f"\n{'=' * 60}")
    print(f"YEAR {year}")
    print(f"{'=' * 60}")
    print(f"Existing XML files: {len(existing_before):,}")
    print(f"First missing roll: {first_missing}")

    downloaded = 0
    skipped = 0
    missing = 0
    invalid = 0
    errors = 0

    consecutive_missing = 0

    progress = tqdm(
        range(first_missing, MAX_ROLL + 1),
        desc=str(year),
        unit="roll",
        ncols=90,
    )

    for roll in progress:
        destination = roll_path(year, roll)

        # This matters when there is a gap earlier in the sequence:
        # after filling that gap, later files may already exist.
        if destination.exists():
            skipped += 1
            consecutive_missing = 0
            continue

        result = download_one(session, year, roll)

        if result == "downloaded":
            downloaded += 1
            consecutive_missing = 0

        elif result == "missing":
            missing += 1
            consecutive_missing += 1

        elif result == "invalid":
            invalid += 1
            consecutive_missing += 1

        else:
            errors += 1

            # Network/server errors should NOT convince us we've
            # reached the end of the roll-call sequence.
            consecutive_missing = 0

        progress.set_postfix(
            new=downloaded,
            skip=skipped,
            miss=missing,
            err=errors,
        )

        if consecutive_missing >= CONSECUTIVE_MISSING_LIMIT:
            progress.close()

            print(
                f"\nStopping {year}: "
                f"{CONSECUTIVE_MISSING_LIMIT} consecutive "
                f"missing/invalid rolls reached."
            )
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    existing_after = existing_roll_numbers(year)

    print(f"\n{year} SUMMARY")
    print(f"  Existing before: {len(existing_before):,}")
    print(f"  Downloaded:      {downloaded:,}")
    print(f"  Skipped:         {skipped:,}")
    print(f"  Missing:         {missing:,}")
    print(f"  Invalid:         {invalid:,}")
    print(f"  Errors:          {errors:,}")
    print(f"  XML files now:   {len(existing_after):,}")

    if existing_after:
        print(
            f"  Local roll span: "
            f"{min(existing_after)}-{max(existing_after)}"
        )


# ============================================================
# COMMAND LINE
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Download U.S. House Clerk roll-call XML files "
            "for one or more calendar years."
        )
    )

    parser.add_argument(
        "years",
        nargs="*",
        type=int,
        help=(
            "Calendar years to download. "
            "Example: 2023 2024. "
            "Defaults to 2025 2026."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    years = args.years or DEFAULT_YEARS
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print("BipartisanCurious Clerk XML downloader")
    print("--------------------------------------")
    print(f"Years: {years}")
    print(
        f"Stop rule: {CONSECUTIVE_MISSING_LIMIT} "
        "consecutive missing/invalid rolls"
    )

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "BipartisanCurious/0.1 "
                    "(House roll-call research project)"
                )
            }
        )

        for year in years:
            download_year(session, year)

    print("\nDownload run complete.")


if __name__ == "__main__":
    main()
