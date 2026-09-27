from pathlib import Path

import pandas as pd


CONGRESS = 119

MEMBER_VOTES_FILE = (
    Path("data/processed/members")
    / f"member_votes_{CONGRESS}.csv"
)

ROLL_STATS_FILE = (
    Path("data/processed/roll_calls")
    / f"roll_call_stats_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/processed/members")
    / f"member_vote_alignment_{CONGRESS}.csv"
)


ROLL_KEY = [
    "congress",
    "session",
    "roll_number",
]


def classify_alignment(row):
    """
    Classify a member's vote relative to the majority position
    of that member's own party.

    This is descriptive only. No weighting or vote-value judgment
    is applied here.
    """

    vote = row["vote"]
    party = row["party"]

    # --------------------------------------------------------
    # Nonstandard roll calls
    # --------------------------------------------------------

    if row["validation_type"] != "party_totals":
        return "nonstandard_roll"

    # --------------------------------------------------------
    # Not Voting / Present / other member choices
    # --------------------------------------------------------

    if vote == "Not Voting":
        return "not_voting"

    if vote == "Present":
        return "present_or_other"

    if vote not in {"Yea", "Nay"}:
        return "present_or_other"

    # --------------------------------------------------------
    # Determine own-party position
    # --------------------------------------------------------

    if party == "Republican":
        own_party_position = row["republican_position"]

    elif party == "Democratic":
        own_party_position = row["democratic_position"]

    else:
        # We are not forcing Independents or any other party
        # into a Democratic/Republican alignment framework.
        return "no_major_party_alignment"

    # --------------------------------------------------------
    # Party has no usable majority position
    # --------------------------------------------------------

    if own_party_position == "No Position":
        return "no_party_position"

    if own_party_position == "Tie":
        return "no_party_majority"

    if own_party_position not in {"Yea", "Nay"}:
        return "no_party_position"

    # --------------------------------------------------------
    # Actual alignment
    # --------------------------------------------------------

    if vote == own_party_position:
        return "with_own_party"

    return "against_own_party"


def get_own_party_position(row):
    party = row["party"]

    if row["validation_type"] != "party_totals":
        return None

    if party == "Republican":
        return row["republican_position"]

    if party == "Democratic":
        return row["democratic_position"]

    return None


def get_own_party_majority_strength(row):
    party = row["party"]

    if row["validation_type"] != "party_totals":
        return None

    if party == "Republican":
        return row["republican_majority_strength"]

    if party == "Democratic":
        return row["democratic_majority_strength"]

    return None


def get_other_major_party_position(row):
    party = row["party"]

    if row["validation_type"] != "party_totals":
        return None

    if party == "Republican":
        return row["democratic_position"]

    if party == "Democratic":
        return row["republican_position"]

    return None


def main():
    member_votes = pd.read_csv(MEMBER_VOTES_FILE)
    roll_stats = pd.read_csv(ROLL_STATS_FILE)

    print("BipartisanCurious member alignment builder")
    print("------------------------------------------")
    print(f"Member-vote rows loaded: {len(member_votes):,}")
    print(f"Roll-call rows loaded:   {len(roll_stats):,}")

    # --------------------------------------------------------
    # Select roll-level fields needed by member records
    # --------------------------------------------------------

    roll_columns = ROLL_KEY + [
        "validation_type",
        "vote_question",
        "vote_description",
        "legislation_number",
        "action_date",
        "vote_result",

        "house_yea",
        "house_nay",
        "house_present",
        "house_not_voting",
        "house_yea_share_of_yea_nay",
        "house_nay_share_of_yea_nay",

        "republican_position",
        "democratic_position",
        "republican_majority_strength",
        "democratic_majority_strength",

        # Party-unity and vote-context measures
        "party_unity_vote",
        "has_xx_member",
        "parties_opposed",
        "parties_same_side",
        "party_separation",
        "major_party_yea_share_difference",
        "house_margin_share",
    ]

    roll_subset = roll_stats[roll_columns].copy()

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    merged = member_votes.merge(
        roll_subset,
        on=ROLL_KEY,
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched = merged[
        merged["_merge"] != "both"
    ]

    print("\nJOIN CHECK")
    print("----------")
    print(f"Unmatched member rows: {len(unmatched):,}")

    if not unmatched.empty:
        raise RuntimeError(
            "Some member-vote records did not match a roll-call "
            "statistics record."
        )

    merged = merged.drop(columns="_merge")

    # --------------------------------------------------------
    # Member-relative fields
    # --------------------------------------------------------

    merged["own_party_position"] = merged.apply(
        get_own_party_position,
        axis=1,
    )

    merged["other_major_party_position"] = merged.apply(
        get_other_major_party_position,
        axis=1,
    )

    merged["own_party_majority_strength"] = merged.apply(
        get_own_party_majority_strength,
        axis=1,
    )

    merged["alignment"] = merged.apply(
        classify_alignment,
        axis=1,
    )

    # --------------------------------------------------------
    # Useful factual flags
    # --------------------------------------------------------

    merged["cast_yea_or_nay"] = merged["vote"].isin(
        ["Yea", "Nay"]
    )

    merged["cast_any_vote"] = (
        merged["vote"] != "Not Voting"
    )

    merged["is_major_party_member"] = merged["party"].isin(
        ["Republican", "Democratic"]
    )

    merged["against_party_when_parties_opposed"] = (
        (merged["alignment"] == "against_own_party")
        & merged["parties_opposed"].fillna(False)
    )

    merged["against_party_when_parties_same_side"] = (
        (merged["alignment"] == "against_own_party")
        & merged["parties_same_side"].fillna(False)
    )

    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    duplicate_key = [
        "congress",
        "session",
        "roll_number",
        "bioguide_id",
    ]

    duplicate_rows = merged.duplicated(
        subset=duplicate_key,
        keep=False,
    )

    standard_major_party_yea_nay = merged[
        (merged["validation_type"] == "party_totals")
        & merged["is_major_party_member"]
        & merged["cast_yea_or_nay"]
        & merged["own_party_position"].isin(["Yea", "Nay"])
    ]

    bad_alignment = standard_major_party_yea_nay[
        ~standard_major_party_yea_nay["alignment"].isin(
            [
                "with_own_party",
                "against_own_party",
            ]
        )
    ]

    print("\nQUALITY CHECKS")
    print("--------------")
    print(
        f"Duplicate member-roll rows: "
        f"{int(duplicate_rows.sum()):,}"
    )
    print(
        "Unclassified usable major-party Yea/Nay rows: "
        f"{len(bad_alignment):,}"
    )

    if duplicate_rows.any():
        raise RuntimeError(
            "Duplicate member-roll identities detected."
        )

    if not bad_alignment.empty:
        raise RuntimeError(
            "Some usable major-party Yea/Nay votes were not "
            "classified with/against own party."
        )

    # --------------------------------------------------------
    # Diagnostics
    # --------------------------------------------------------

    print("\nALIGNMENT COUNTS")
    print("----------------")
    print(
        merged["alignment"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nAGAINST-PARTY BREAKDOWN")
    print("-----------------------")

    against = merged[
        merged["alignment"] == "against_own_party"
    ]

    print(f"Total against-own-party votes: {len(against):,}")
    print(
        "When major parties opposed:   "
        f"{int(against['parties_opposed'].fillna(False).sum()):,}"
    )
    print(
        "When major parties same side: "
        f"{int(against['parties_same_side'].fillna(False).sum()):,}"
    )

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    merged.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(f"Rows written: {len(merged):,}")
    print(f"Columns written: {len(merged.columns):,}")

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
