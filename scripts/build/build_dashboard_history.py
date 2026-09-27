import json
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = (
    Path("data/processed/members")
    / "member_historical_summaries_115_119.csv"
)

OUTPUT_FILE = (
    Path("docs/data")
    / "member_history.json"
)


# These are the periods we want exposed in the dashboard.
#
# Obama (partial) remains in the analytical dataset so that
# Jan. 3-19, 2017 votes are assigned correctly, but it is not
# presented as a comparable presidential period in the UI.
DASHBOARD_PERIODS = [
    ("congress", "115"),
    ("congress", "116"),
    ("congress", "117"),
    ("congress", "118"),
    ("congress", "119"),
    ("presidential", "trump_1"),
    ("presidential", "biden"),
    ("presidential", "trump_2"),
    ("all_available", "2017_present"),
]


PERIOD_METADATA = {
    ("congress", "115"): {
        "label": "115th Congress",
        "group": "Congress",
    },
    ("congress", "116"): {
        "label": "116th Congress",
        "group": "Congress",
    },
    ("congress", "117"): {
        "label": "117th Congress",
        "group": "Congress",
    },
    ("congress", "118"): {
        "label": "118th Congress",
        "group": "Congress",
    },
    ("congress", "119"): {
        "label": "119th Congress",
        "group": "Congress",
    },
    ("presidential", "trump_1"): {
        "label": "Trump I",
        "group": "Presidency",
    },
    ("presidential", "biden"): {
        "label": "Biden",
        "group": "Presidency",
    },
    ("presidential", "trump_2"): {
        "label": "Trump II",
        "group": "Presidency",
    },
    ("all_available", "2017_present"): {
        "label": "2017-present",
        "group": "Overall",
    },
}


# ============================================================
# HELPERS
# ============================================================

def clean_int(value):
    if pd.isna(value):
        return None

    return int(value)


def clean_float(value):
    if pd.isna(value):
        return None

    return float(value)


def clean_bool(value):
    if pd.isna(value):
        return None

    return bool(value)


def clean_string(value):
    if pd.isna(value):
        return None

    return str(value)


def build_record(row):
    return {
        "name": clean_string(row["representative"]),
        "state": clean_string(row["state"]),
        "party": clean_string(row["party"]),
        "party_code": clean_string(row["party_code"]),

        "parties_during_period": clean_string(
            row["parties_during_period"]
        ),

        "party_changed_during_period": clean_bool(
            row["party_changed_during_period"]
        ),

        "first_vote_date": clean_string(
            row["first_vote_date"]
        ),

        "last_vote_date": clean_string(
            row["last_vote_date"]
        ),

        "opportunities": clean_int(
            row["party_unity_opportunities"]
        ),

        "votes_cast": clean_int(
            row["party_unity_votes_cast"]
        ),

        "not_voting": clean_int(
            row["party_unity_not_voting"]
        ),

        "present_or_other": clean_int(
            row["party_unity_present_or_other"]
        ),

        "with_party": clean_int(
            row["with_own_party_unity"]
        ),

        "against_party": clean_int(
            row["against_own_party_unity"]
        ),

        "unity_rate": clean_float(
            row["party_unity_rate"]
        ),

        "opposition_rate": clean_float(
            row["party_opposition_rate"]
        ),

        "participation_rate": clean_float(
            row["party_unity_participation_rate"]
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing historical summary file: {INPUT_FILE}\n"
            "Run build_historical_member_summaries.py first."
        )

    df = pd.read_csv(
        INPUT_FILE,
        low_memory=False,
    )

    print("BipartisanCurious dashboard history builder")
    print("-------------------------------------------")
    print(f"Historical rows loaded: {len(df):,}")

    wanted = set(DASHBOARD_PERIODS)

    df["_period_key"] = list(
        zip(
            df["period_type"].astype(str),
            df["period_id"].astype(str),
        )
    )

    dashboard = df[
        df["_period_key"].isin(wanted)
    ].copy()

    print(
        f"Dashboard rows selected: {len(dashboard):,}"
    )

    # --------------------------------------------------------
    # Verify requested periods
    # --------------------------------------------------------

    observed_periods = set(
        dashboard["_period_key"].unique()
    )

    missing_periods = wanted - observed_periods

    if missing_periods:
        raise RuntimeError(
            "Missing dashboard periods: "
            f"{sorted(missing_periods)}"
        )

    # --------------------------------------------------------
    # Build compact nested structure
    #
    # periods -> period key -> members -> Bioguide ID
    # --------------------------------------------------------

    output = {
        "period_order": [],
        "periods": {},
    }

    for period_type, period_id in DASHBOARD_PERIODS:
        key = f"{period_type}:{period_id}"

        metadata = PERIOD_METADATA[
            (period_type, period_id)
        ]

        period_df = dashboard[
            (dashboard["period_type"] == period_type)
            & (
                dashboard["period_id"].astype(str)
                == period_id
            )
        ].copy()

        duplicate_ids = period_df.duplicated(
            subset=["bioguide_id"],
            keep=False,
        )

        if duplicate_ids.any():
            raise RuntimeError(
                f"Duplicate Bioguide IDs in {key}"
            )

        members = {}

        for _, row in period_df.iterrows():
            bioguide_id = str(row["bioguide_id"])

            members[bioguide_id] = build_record(row)

        output["period_order"].append(key)

        output["periods"][key] = {
            "type": period_type,
            "id": period_id,
            "label": metadata["label"],
            "group": metadata["group"],

            "start_date": clean_string(
                period_df["period_start"].iloc[0]
            ),

            "end_date": clean_string(
                period_df["period_end"].iloc[0]
            ),

            "partial_period": clean_bool(
                period_df["partial_period"].iloc[0]
            ),

            "member_count": len(members),
            "members": members,
        }

    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    total_exported = sum(
        period["member_count"]
        for period in output["periods"].values()
    )

    expected_rows = len(dashboard)

    print("\nQUALITY CHECKS")
    print("--------------")
    print(
        f"Requested periods: {len(DASHBOARD_PERIODS)}"
    )
    print(
        f"Periods written:   {len(output['periods'])}"
    )
    print(
        f"Expected member-period rows: {expected_rows:,}"
    )
    print(
        f"Exported member-period rows: {total_exported:,}"
    )

    if len(output["periods"]) != len(DASHBOARD_PERIODS):
        raise RuntimeError(
            "Dashboard period count mismatch."
        )

    if total_exported != expected_rows:
        raise RuntimeError(
            "Dashboard member-period row count mismatch."
        )

    # --------------------------------------------------------
    # Fitzpatrick diagnostic
    # --------------------------------------------------------

    print("\nFITZPATRICK CHECK")
    print("-----------------")

    for key in output["period_order"]:
        period = output["periods"][key]

        fitz = period["members"].get(
            "F000466"
        )

        if fitz is None:
            print(
                f"{period['label']}: not present"
            )
            continue

        print(
            f"{period['label']}: "
            f"{fitz['against_party']}/"
            f"{fitz['votes_cast']} against | "
            f"{fitz['opposition_rate']:.6f}"
        )

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = OUTPUT_FILE.with_suffix(
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

    temp_path.replace(OUTPUT_FILE)

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(
        f"File size: "
        f"{OUTPUT_FILE.stat().st_size / 1024:.1f} KB"
    )

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
