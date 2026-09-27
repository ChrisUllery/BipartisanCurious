from pathlib import Path
import sys

import pandas as pd
from tqdm import tqdm


# Allow this script to import parse_roll_call.py from the same directory.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from parse_roll_call import parse_roll_call


# ============================================================
# CONFIG
# ============================================================

CONGRESS = 119

RAW_ROOT = Path("data/raw/clerk_xml")

ROLL_CALL_OUTPUT = (
    Path("data/processed/roll_calls")
    / f"roll_calls_{CONGRESS}.csv"
)

MEMBER_VOTE_OUTPUT = (
    Path("data/processed/members")
    / f"member_votes_{CONGRESS}.csv"
)

VALIDATION_OUTPUT = (
    Path("data/diagnostics")
    / f"xml_validation_{CONGRESS}.csv"
)

YEARS = [2025, 2026]

EXPECTED_PARTIES = {
    "Republican",
    "Democratic",
    "Independent",
}

EXPECTED_VOTES = {
    "Yea",
    "Nay",
    "Present",
    "Not Voting",
}


# ============================================================
# HELPERS
# ============================================================

def atomic_write_csv(df, path):
    """Write a CSV through a temporary file to avoid partial outputs."""
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp_path, index=False)
    temp_path.replace(path)


def get_xml_files():
    """Collect all raw Clerk XML files for the configured years."""
    files = []

    for year in YEARS:
        year_dir = RAW_ROOT / str(year)

        if not year_dir.exists():
            print(f"WARNING: Raw XML directory does not exist: {year_dir}")
            continue

        files.extend(year_dir.glob("roll*.xml"))

    def sort_key(path):
        year = int(path.parent.name)
        roll_text = path.stem.removeprefix("roll")
        roll = int(roll_text) if roll_text.isdigit() else 999999

        return year, roll

    return sorted(files, key=sort_key)


def build_roll_call_row(metadata, member_votes):
    """
    Build one canonical roll-call row.

    Party counts are calculated from individual member records.
    """
    row = metadata.copy()

    for party_key in [
        "republican",
        "democratic",
        "independent",
    ]:
        for vote_key in [
            "yea",
            "nay",
            "present",
            "not_voting",
        ]:
            row[f"{party_key}_{vote_key}"] = 0

    party_prefix = {
        "Republican": "republican",
        "Democratic": "democratic",
        "Independent": "independent",
    }

    vote_suffix = {
        "Yea": "yea",
        "Nay": "nay",
        "Present": "present",
        "Not Voting": "not_voting",
    }

    for (party, vote), count in (
        member_votes.groupby(["party", "vote"], dropna=False)
        .size()
        .items()
    ):
        if party in party_prefix and vote in vote_suffix:
            column = (
                f"{party_prefix[party]}_"
                f"{vote_suffix[vote]}"
            )
            row[column] = int(count)

    row["member_records"] = len(member_votes)

    row["total_yea"] = int(
        (member_votes["vote"] == "Yea").sum()
    )
    row["total_nay"] = int(
        (member_votes["vote"] == "Nay").sum()
    )
    row["total_present"] = int(
        (member_votes["vote"] == "Present").sum()
    )
    row["total_not_voting"] = int(
        (member_votes["vote"] == "Not Voting").sum()
    )

    return row


# ============================================================
# MAIN BUILD
# ============================================================

def main():
    xml_files = get_xml_files()

    if not xml_files:
        raise FileNotFoundError(
            f"No Clerk XML files found under {RAW_ROOT}"
        )

    print("BipartisanCurious canonical dataset builder")
    print("-------------------------------------------")
    print(f"Congress: {CONGRESS}")
    print(f"XML files found: {len(xml_files):,}")

    roll_call_rows = []
    member_frames = []
    validation_frames = []

    parse_errors = []

    unexpected_parties = set()
    unexpected_party_codes = set()
    unexpected_votes = set()

    missing_bioguide_rows = []

    for xml_path in tqdm(
        xml_files,
        desc="Parsing XML",
        unit="roll",
        ncols=90,
    ):
        try:
            metadata, member_votes, validation = parse_roll_call(
                xml_path
            )

        except Exception as exc:
            parse_errors.append(
                {
                    "source_file": str(xml_path),
                    "error": repr(exc),
                }
            )
            continue

        # Only build the requested Congress.
        if metadata["congress"] != CONGRESS:
            print(
                f"\nWARNING: Skipping {xml_path}: "
                f"XML says Congress {metadata['congress']}"
            )
            continue

        # --------------------------------------------
        # Identity diagnostics
        # --------------------------------------------

        missing_ids = member_votes[
            member_votes["bioguide_id"].isna()
            | (
                member_votes["bioguide_id"]
                .astype(str)
                .str.strip()
                == ""
            )
        ]

        if not missing_ids.empty:
            for _, row in missing_ids.iterrows():
                missing_bioguide_rows.append(
                    {
                        "source_file": str(xml_path),
                        "congress": row["congress"],
                        "session": row["session"],
                        "roll_number": row["roll_number"],
                        "representative": row["representative"],
                        "party": row["party"],
                        "state": row["state"],
                    }
                )

        # --------------------------------------------
        # Unexpected values
        # --------------------------------------------

        observed_parties = set(
            member_votes["party"].dropna().unique()
        )

        unexpected_parties.update(
            observed_parties - EXPECTED_PARTIES
        )

        observed_party_codes = set(
            member_votes["party_code"].dropna().unique()
        )

        unexpected_party_codes.update(
            observed_party_codes - {"R", "D", "I"}
        )

        observed_votes = set(
            member_votes["vote"].dropna().unique()
        )

        validation_types = set(
            validation["validation_type"].dropna().unique()
        )

        if len(validation_types) != 1:
            raise ValueError(
                f"{xml_path}: expected exactly one validation type, "
                f"found {sorted(validation_types)}"
            )

        validation_type = next(iter(validation_types))

        # Standard party-total roll calls should contain only the
        # ordinary House vote choices. Candidate-total votes, such
        # as Speaker elections, legitimately contain candidate names.
        if validation_type == "party_totals":
            unexpected_votes.update(
                observed_votes - EXPECTED_VOTES
            )

        elif validation_type != "candidate_totals":
            raise ValueError(
                f"{xml_path}: unsupported validation type "
                f"{validation_type!r}"
            )

        # --------------------------------------------
        # Roll-call row
        # --------------------------------------------

        roll_call_row = build_roll_call_row(
            metadata,
            member_votes,
        )

        roll_call_row["validation_type"] = validation_type

        roll_call_rows.append(roll_call_row)

        # --------------------------------------------
        # Member records
        # --------------------------------------------

        member_votes = member_votes.copy()
        member_votes["source_file"] = str(xml_path)

        member_frames.append(member_votes)

        # --------------------------------------------
        # Validation records
        # --------------------------------------------

        validation = validation.copy()

        validation.insert(
            0,
            "roll_number",
            metadata["roll_number"],
        )
        validation.insert(
            0,
            "session",
            metadata["session"],
        )
        validation.insert(
            0,
            "congress",
            metadata["congress"],
        )

        validation["source_file"] = str(xml_path)

        validation_frames.append(validation)

    # ========================================================
    # COMBINE
    # ========================================================

    if parse_errors:
        print("\nPARSE ERRORS")
        print("------------")

        for error in parse_errors:
            print(
                f"{error['source_file']}: "
                f"{error['error']}"
            )

        raise RuntimeError(
            f"{len(parse_errors)} XML file(s) failed to parse. "
            "No canonical outputs were written."
        )

    roll_calls = pd.DataFrame(roll_call_rows)

    member_votes_all = pd.concat(
        member_frames,
        ignore_index=True,
    )

    validation_all = pd.concat(
        validation_frames,
        ignore_index=True,
    )

    # ========================================================
    # SORT
    # ========================================================

    session_order = {
        "1st": 1,
        "2nd": 2,
    }

    roll_calls["_session_order"] = (
        roll_calls["session"]
        .map(session_order)
        .fillna(99)
    )

    roll_calls = (
        roll_calls
        .sort_values(
            ["_session_order", "roll_number"]
        )
        .drop(columns="_session_order")
        .reset_index(drop=True)
    )

    member_votes_all["_session_order"] = (
        member_votes_all["session"]
        .map(session_order)
        .fillna(99)
    )

    member_votes_all = (
        member_votes_all
        .sort_values(
            [
                "_session_order",
                "roll_number",
                "bioguide_id",
            ]
        )
        .drop(columns="_session_order")
        .reset_index(drop=True)
    )

    validation_all["_session_order"] = (
        validation_all["session"]
        .map(session_order)
        .fillna(99)
    )

    validation_all = (
        validation_all
        .sort_values(
            [
                "_session_order",
                "roll_number",
                "party",
            ]
        )
        .drop(columns="_session_order")
        .reset_index(drop=True)
    )

    # ========================================================
    # QUALITY CHECKS
    # ========================================================

    roll_key = [
        "congress",
        "session",
        "roll_number",
    ]

    member_key = [
        "congress",
        "session",
        "roll_number",
        "bioguide_id",
    ]

    duplicate_rolls = roll_calls.duplicated(
        subset=roll_key,
        keep=False,
    )

    duplicate_member_votes = member_votes_all.duplicated(
        subset=member_key,
        keep=False,
    )

    validation_failures = validation_all[
        ~validation_all["all_match"]
    ]

    distinct_rolls = (
        roll_calls[roll_key]
        .drop_duplicates()
        .shape[0]
    )

    print("\nQUALITY CHECKS")
    print("--------------")
    print(f"Distinct roll calls: {distinct_rolls:,}")
    print(f"Member vote rows:    {len(member_votes_all):,}")
    print(
        f"Duplicate roll rows: "
        f"{int(duplicate_rolls.sum()):,}"
    )
    print(
        f"Duplicate member-vote rows: "
        f"{int(duplicate_member_votes.sum()):,}"
    )
    print(
        f"Missing Bioguide IDs: "
        f"{len(missing_bioguide_rows):,}"
    )
    print(
        f"Validation failures: "
        f"{len(validation_failures):,}"
    )

    print(
        "Unexpected normalized parties: "
        f"{sorted(unexpected_parties) if unexpected_parties else 'None'}"
    )
    print(
        "Unexpected raw party codes: "
        f"{sorted(unexpected_party_codes) if unexpected_party_codes else 'None'}"
    )
    print(
        "Unexpected vote values: "
        f"{sorted(unexpected_votes) if unexpected_votes else 'None'}"
    )

    # ========================================================
    # HARD FAILURES
    # ========================================================

    problems = []

    if duplicate_rolls.any():
        problems.append(
            "duplicate roll-call identities"
        )

    if duplicate_member_votes.any():
        problems.append(
            "duplicate member-vote identities"
        )

    if missing_bioguide_rows:
        problems.append(
            "missing Bioguide IDs"
        )

    if not validation_failures.empty:
        problems.append(
            "Clerk total validation failures"
        )

    if unexpected_votes:
        problems.append(
            "unexpected vote values"
        )

    if unexpected_parties:
        problems.append(
            "unexpected normalized party values"
        )

    if unexpected_party_codes:
        problems.append(
            "unexpected raw party codes"
        )

    if problems:
        print("\nBUILD STOPPED")
        print("-------------")

        for problem in problems:
            print(f"- {problem}")

        print(
            "\nCanonical outputs were NOT written. "
            "Inspect the diagnostics above first."
        )

        return

    # ========================================================
    # WRITE OUTPUTS
    # ========================================================

    atomic_write_csv(
        roll_calls,
        ROLL_CALL_OUTPUT,
    )

    atomic_write_csv(
        member_votes_all,
        MEMBER_VOTE_OUTPUT,
    )

    atomic_write_csv(
        validation_all,
        VALIDATION_OUTPUT,
    )

    print("\nOUTPUTS")
    print("-------")
    print(f"Roll calls:   {ROLL_CALL_OUTPUT}")
    print(f"Member votes: {MEMBER_VOTE_OUTPUT}")
    print(f"Validation:   {VALIDATION_OUTPUT}")

    print("\nBUILD PASSED")
    print(
        "All parsed member totals match the Clerk XML "
        "and no blocking identity/schema problems were found."
    )


if __name__ == "__main__":
    main()
