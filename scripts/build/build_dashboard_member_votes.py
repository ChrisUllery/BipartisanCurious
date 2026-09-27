from pathlib import Path
import json

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

CONGRESSES = range(115, 120)

INPUT_DIR = Path("data/processed/members")
OUTPUT_DIR = Path("docs/data/member_votes")

ALLOWED_ALIGNMENTS = {
    "with_own_party",
    "against_own_party",
    "not_voting",
    "present_or_other",
}


# ============================================================
# HELPERS
# ============================================================

def clean_string(value):
    if pd.isna(value):
        return None

    return str(value)


def clean_int(value):
    if pd.isna(value):
        return None

    return int(value)


def clean_bool(value):
    if pd.isna(value):
        return False

    return bool(value)


def clerk_url(action_date, roll_number):
    """
    House Clerk vote pages use:
        https://clerk.house.gov/Votes/YYYYROLL

    Example:
        2025 + roll 6
        https://clerk.house.gov/Votes/20256
    """

    date = pd.to_datetime(
        action_date,
        format="mixed",
        dayfirst=True,
        errors="raise",
    )

    return (
        "https://clerk.house.gov/Votes/"
        f"{date.year}{int(roll_number)}"
    )


def detail_category(row):
    """
    Give each exported row one primary display category.

    against_both_party_majorities is a special subtype of
    against_own_party that occurs when Republican and
    Democratic majorities took the same position.
    """

    alignment = row["alignment"]

    if (
        alignment == "against_own_party"
        and clean_bool(
            row["against_party_when_parties_same_side"]
        )
    ):
        return "against_both_party_majorities"

    if (
        alignment == "against_own_party"
        and clean_bool(
            row["against_party_when_parties_opposed"]
        )
    ):
        return "against_own_party_majority"

    if alignment == "with_own_party":
        return "with_own_party_majority"

    if alignment == "not_voting":
        return "not_voting"

    if alignment == "present_or_other":
        return "present_or_other"

    return None


def build_vote_record(row):
    category = detail_category(row)

    return {
        "date": clean_string(row["action_date"]),
        "congress": clean_int(row["congress"]),
        "session": clean_string(row["session"]),
        "roll_number": clean_int(row["roll_number"]),

        "party": clean_string(row["party"]),
        "party_code": clean_string(row["party_code"]),

        "vote": clean_string(row["vote"]),

        "republican_position": clean_string(
            row["republican_position"]
        ),
        "democratic_position": clean_string(
            row["democratic_position"]
        ),

        "own_party_position": clean_string(
            row["own_party_position"]
        ),
        "other_major_party_position": clean_string(
            row["other_major_party_position"]
        ),

        "parties_opposed": clean_bool(
            row["parties_opposed"]
        ),
        "parties_same_side": clean_bool(
            row["parties_same_side"]
        ),

        "alignment": clean_string(
            row["alignment"]
        ),

        "category": category,

        "against_party_when_parties_opposed": clean_bool(
            row["against_party_when_parties_opposed"]
        ),

        "against_party_when_parties_same_side": clean_bool(
            row["against_party_when_parties_same_side"]
        ),

        "vote_question": clean_string(
            row["vote_question"]
        ),

        "vote_description": clean_string(
            row["vote_description"]
        ),

        "legislation_number": clean_string(
            row["legislation_number"]
        ),

        "clerk_url": clerk_url(
            row["action_date"],
            row["roll_number"],
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    frames = []

    for congress in CONGRESSES:
        path = (
            INPUT_DIR
            / f"member_vote_alignment_{congress}.csv"
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Missing alignment file: {path}"
            )

        df = pd.read_csv(
            path,
            low_memory=False,
        )

        df["_source_congress"] = congress

        frames.append(df)

    votes = pd.concat(
        frames,
        ignore_index=True,
    )

    print("BipartisanCurious member vote-detail builder")
    print("-------------------------------------------")
    print(f"Rows loaded: {len(votes):,}")

    # --------------------------------------------------------
    # Keep usable major-party member records.
    #
    # We intentionally DO NOT filter on party_unity_vote.
    # Same-side votes are necessary for the
    # against_both_party_majorities category.
    # --------------------------------------------------------

    # Export only votes useful for the member verification
    # page:
    #
    # 1. Member voted against their party majority when the
    #    Republican and Democratic majorities disagreed.
    #
    # 2. Member voted against the shared position of both
    #    major-party majorities.
    #
    # 3. Member did not vote when the Republican and
    #    Democratic majorities disagreed.
    #
    # Routine votes with the member's own party are already
    # represented in the dashboard summaries and do not need
    # to be duplicated in the detail files.

    opposed_against = (
        votes["against_party_when_parties_opposed"]
        .fillna(False)
        .astype(bool)
    )

    same_side_against = (
        votes["against_party_when_parties_same_side"]
        .fillna(False)
        .astype(bool)
    )

    missed_party_unity = (
        votes["party_unity_vote"]
        .fillna(False)
        .astype(bool)
        & votes["alignment"].eq("not_voting")
    )

    detail = votes[
        votes["party"].isin(
            ["Republican", "Democratic"]
        )
        & (
            opposed_against
            | same_side_against
            | missed_party_unity
        )
    ].copy()

    detail["category"] = detail.apply(
        detail_category,
        axis=1,
    )

    detail = detail[
        detail["category"].notna()
    ].copy()

    print(f"Rows selected: {len(detail):,}")

    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    duplicate_mask = detail.duplicated(
        subset=[
            "bioguide_id",
            "congress",
            "session",
            "roll_number",
        ],
        keep=False,
    )

    duplicate_count = int(
        duplicate_mask.sum()
    )

    bad_same_side = detail[
        (
            detail["category"]
            == "against_both_party_majorities"
        )
        & (
            ~detail["parties_same_side"]
            .fillna(False)
            .astype(bool)
        )
    ]

    bad_opposed = detail[
        (
            detail["category"]
            == "against_own_party_majority"
        )
        & (
            ~detail["parties_opposed"]
            .fillna(False)
            .astype(bool)
        )
    ]

    same_side_position_mismatches = detail[
        (
            detail["category"]
            == "against_both_party_majorities"
        )
        & (
            detail["republican_position"]
            != detail["democratic_position"]
        )
    ]

    print("\nQUALITY CHECKS")
    print("--------------")
    print(
        "Duplicate member-roll rows: "
        f"{duplicate_count:,}"
    )
    print(
        "Bad against-both classifications: "
        f"{len(bad_same_side):,}"
    )
    print(
        "Bad opposed-party classifications: "
        f"{len(bad_opposed):,}"
    )
    print(
        "Same-side position mismatches: "
        f"{len(same_side_position_mismatches):,}"
    )

    if duplicate_count:
        raise RuntimeError(
            "Duplicate member-roll rows found."
        )

    if len(bad_same_side):
        raise RuntimeError(
            "Invalid against-both classifications found."
        )

    if len(bad_opposed):
        raise RuntimeError(
            "Invalid against-own-party classifications found."
        )

    if len(same_side_position_mismatches):
        raise RuntimeError(
            "Against-both rows do not have matching "
            "Republican/Democratic positions."
        )

    # --------------------------------------------------------
    # Prepare output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # One JSON file per member
    # --------------------------------------------------------

    files_written = 0
    exported_rows = 0

    category_totals = {
        "against_own_party_majority": 0,
        "against_both_party_majorities": 0,
        "not_voting": 0,
    }

    for bioguide_id, group in detail.groupby(
        "bioguide_id",
        sort=True,
    ):
        group = group.copy()

        group["_date_sort"] = pd.to_datetime(
            group["action_date"],
            format="mixed",
            dayfirst=True,
            errors="raise",
        )

        group = group.sort_values(
            [
                "_date_sort",
                "congress",
                "roll_number",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )

        records = [
            build_vote_record(row)
            for _, row in group.iterrows()
        ]

        counts = (
            group["category"]
            .value_counts()
            .to_dict()
        )

        # ----------------------------------------------------
        # Pre-group detail records for the website.
        #
        # The browser should not have to classify or organize
        # votes. Python does that work here during the build.
        #
        # Structure:
        #
        # categories
        #   -> category
        #       -> Congress number
        #           -> list of vote records
        # ----------------------------------------------------

        categories = {
            "against_own_party_majority": {},
            "against_both_party_majorities": {},
            "not_voting": {},
        }

        for record in records:
            category = record["category"]
            congress_key = str(record["congress"])

            if category not in categories:
                raise RuntimeError(
                    "Unexpected detail category: "
                    f"{category}"
                )

            categories[category].setdefault(
                congress_key,
                []
            ).append(record)

        for category in category_totals:
            category_totals[category] += int(
                counts.get(category, 0)
            )

        parties = [
            str(value)
            for value in group["party"].dropna().unique()
        ]

        names = [
            str(value)
            for value
            in group["representative"].dropna().unique()
        ]

        output = {
            "bioguide_id": str(bioguide_id),

            "names_in_data": names,

            "parties_in_data": parties,

            "first_vote_date": clean_string(
                group.iloc[-1]["action_date"]
            ),

            "last_vote_date": clean_string(
                group.iloc[0]["action_date"]
            ),

            "counts": {
                category: int(
                    counts.get(category, 0)
                )
                for category in category_totals
            },

            "categories": categories,
        }

        output_path = (
            OUTPUT_DIR
            / f"{bioguide_id}.json"
        )

        temp_path = output_path.with_suffix(
            ".json.tmp"
        )

        temp_path.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        temp_path.replace(output_path)

        files_written += 1
        exported_rows += len(records)

    # --------------------------------------------------------
    # Final diagnostics
    # --------------------------------------------------------

    print("\nCATEGORY TOTALS")
    print("---------------")

    for category, count in category_totals.items():
        print(
            f"{category}: {count:,}"
        )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_DIR)
    print(f"Member files written: {files_written:,}")
    print(f"Vote records written: {exported_rows:,}")

    if exported_rows != len(detail):
        raise RuntimeError(
            "Exported vote-record count does not "
            "match selected rows."
        )

    # --------------------------------------------------------
    # Fitzpatrick test case
    # --------------------------------------------------------

    fitz_path = OUTPUT_DIR / "F000466.json"

    if fitz_path.exists():
        fitz = json.loads(
            fitz_path.read_text(
                encoding="utf-8"
            )
        )

        fitz_same = (
            fitz["categories"]
            ["against_both_party_majorities"]
            .get("119", [])
        )

        print("\nFITZPATRICK 119 CHECK")
        print("---------------------")
        print(
            "Against both party majorities: "
            f"{len(fitz_same)}"
        )

        for vote in fitz_same:
            print(
                f"{vote['date']} | "
                f"Roll {vote['roll_number']} | "
                f"Fitzpatrick: {vote['vote']} | "
                f"R: {vote['republican_position']} | "
                f"D: {vote['democratic_position']} | "
                f"{vote['legislation_number']}"
            )

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
