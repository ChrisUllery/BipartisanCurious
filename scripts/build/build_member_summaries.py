from pathlib import Path
import argparse

import pandas as pd


DEFAULT_CONGRESS = 119


MEMBER_KEY = [
    "bioguide_id",
]


def safe_rate(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def summarize_member(group):
    # --------------------------------------------------------
    # All recorded roll calls
    # --------------------------------------------------------

    total_roll_calls = len(group)

    yea_votes = (group["vote"] == "Yea").sum()
    nay_votes = (group["vote"] == "Nay").sum()
    present_votes = (group["vote"] == "Present").sum()
    not_voting = (group["vote"] == "Not Voting").sum()

    yea_nay_votes_cast = group["cast_yea_or_nay"].sum()

    # --------------------------------------------------------
    # All ordinary votes with a usable own-party majority
    # --------------------------------------------------------

    usable_alignment = group[
        group["alignment"].isin(
            ["with_own_party", "against_own_party"]
        )
    ]

    with_own_party_all = (
        usable_alignment["alignment"] == "with_own_party"
    ).sum()

    against_own_party_all = (
        usable_alignment["alignment"] == "against_own_party"
    ).sum()

    # --------------------------------------------------------
    # Party-unity vote universe
    #
    # A party-unity vote is a standard Yea/Nay roll call where
    # the Republican and Democratic voting majorities take
    # opposite positions.
    # --------------------------------------------------------

    unity = group[
        group["party_unity_vote"].fillna(False)
        & group["alignment"].isin(
            [
                "with_own_party",
                "against_own_party",
                "not_voting",
                "present_or_other",
            ]
        )
        & group["party"].isin(
            ["Republican", "Democratic"]
        )
    ]

    party_unity_opportunities = len(unity)

    unity_cast = unity[
        unity["cast_yea_or_nay"]
    ]

    party_unity_votes_cast = len(unity_cast)

    party_unity_not_voting = (
        unity["alignment"] == "not_voting"
    ).sum()

    party_unity_present_or_other = (
        unity["alignment"] == "present_or_other"
    ).sum()

    with_own_party_unity = (
        unity_cast["alignment"] == "with_own_party"
    ).sum()

    against_own_party_unity = (
        unity_cast["alignment"] == "against_own_party"
    ).sum()

    # --------------------------------------------------------
    # Return descriptive member summary
    # --------------------------------------------------------

    return pd.Series(
        {
            "total_roll_calls": total_roll_calls,

            "yea_votes": int(yea_votes),
            "nay_votes": int(nay_votes),
            "present_votes": int(present_votes),
            "not_voting": int(not_voting),
            "yea_nay_votes_cast": int(yea_nay_votes_cast),

            "with_own_party_all": int(with_own_party_all),
            "against_own_party_all": int(against_own_party_all),

            "party_unity_opportunities": int(
                party_unity_opportunities
            ),
            "party_unity_votes_cast": int(
                party_unity_votes_cast
            ),
            "party_unity_not_voting": int(
                party_unity_not_voting
            ),
            "party_unity_present_or_other": int(
                party_unity_present_or_other
            ),

            "with_own_party_unity": int(
                with_own_party_unity
            ),
            "against_own_party_unity": int(
                against_own_party_unity
            ),

            "party_unity_rate": safe_rate(
                with_own_party_unity,
                party_unity_votes_cast,
            ),

            "party_opposition_rate": safe_rate(
                against_own_party_unity,
                party_unity_votes_cast,
            ),

            "party_unity_participation_rate": safe_rate(
                party_unity_votes_cast,
                party_unity_opportunities,
            ),
        }
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build member party-alignment summaries "
            "for one Congress."
        )
    )

    parser.add_argument(
        "--congress",
        type=int,
        default=DEFAULT_CONGRESS,
        help="Congress number to build. Defaults to 119.",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    congress = args.congress

    input_file = (
        Path("data/processed/members")
        / f"member_vote_alignment_{congress}.csv"
    )

    output_file = (
        Path("data/processed/members")
        / f"member_summaries_{congress}.csv"
    )

    df = pd.read_csv(
        input_file,
        low_memory=False,
    )

    print("BipartisanCurious member summary builder")
    print("----------------------------------------")
    print(f"Congress: {congress}")
    print(f"Member-vote rows loaded: {len(df):,}")

    # --------------------------------------------------------
    # Member identity and display metadata
    #
    # Bioguide ID is the durable identity. Party affiliation and
    # Clerk display names can change within a Congress.
    #
    # Calculations below use each roll's contemporaneous party.
    # Display metadata uses the last observed record.
    # --------------------------------------------------------

    # Parse Clerk action dates for chronological ordering.
    # The source field uses strings such as "9-Jul-2019", which
    # cannot be sorted correctly as plain text.
    ordered = df.copy()

    ordered["_action_date_sort"] = pd.to_datetime(
        ordered["action_date"],
        format="%d-%b-%Y",
        errors="coerce",
    )

    bad_action_dates = ordered[
        ordered["action_date"].notna()
        & ordered["_action_date_sort"].isna()
    ]

    if not bad_action_dates.empty:
        examples = (
            bad_action_dates["action_date"]
            .drop_duplicates()
            .head(10)
            .tolist()
        )

        raise RuntimeError(
            "Could not parse one or more action_date values. "
            f"Examples: {examples}"
        )

    ordered = ordered.sort_values(
        [
            "bioguide_id",
            "_action_date_sort",
            "roll_number",
        ],
        na_position="first",
    )

    latest_lookup = (
        ordered.groupby(
            "bioguide_id",
            sort=False,
        )
        .tail(1)[
            [
                "bioguide_id",
                "representative",
                "party",
                "party_code",
                "state",
            ]
        ]
        .rename(
            columns={
                "party": "party",
                "party_code": "party_code",
            }
        )
    )

    # Record every distinct party observed for each member during
    # the Congress. Preserve chronological first-observed order.
    party_history = (
        ordered[
            [
                "bioguide_id",
                "party",
            ]
        ]
        .dropna(subset=["party"])
        .drop_duplicates(
            subset=[
                "bioguide_id",
                "party",
            ],
            keep="first",
        )
        .groupby(
            "bioguide_id",
            sort=False,
        )["party"]
        .agg("|".join)
        .rename("parties_during_congress")
        .reset_index()
    )

    party_counts = (
        ordered.groupby(
            "bioguide_id",
            sort=False,
        )["party"]
        .nunique(dropna=True)
        .rename("_party_count")
        .reset_index()
    )

    # Include anyone who belonged to a major party at some point
    # during the Congress. This retains Independent-period records
    # for party switchers without treating those rolls as major-
    # party alignment opportunities.
    major_member_ids = (
        df.loc[
            df["party"].isin(
                ["Republican", "Democratic"]
            ),
            "bioguide_id",
        ]
        .dropna()
        .unique()
    )

    analysis = df[
        df["bioguide_id"].isin(
            major_member_ids
        )
    ].copy()

    summary = (
        analysis.groupby(
            MEMBER_KEY,
            dropna=False,
            sort=True,
        )
        .apply(
            summarize_member,
            include_groups=False,
        )
        .reset_index()
    )

    summary = summary.merge(
        latest_lookup,
        on="bioguide_id",
        how="left",
        validate="one_to_one",
    )

    summary = summary.merge(
        party_history,
        on="bioguide_id",
        how="left",
        validate="one_to_one",
    )

    summary = summary.merge(
        party_counts,
        on="bioguide_id",
        how="left",
        validate="one_to_one",
    )

    summary["party_changed_during_congress"] = (
        summary["_party_count"] > 1
    )

    summary = summary.drop(
        columns="_party_count"
    )

    # Keep identity and party-history fields at the front.
    front_columns = [
        "bioguide_id",
        "representative",
        "party",
        "party_code",
        "state",
        "parties_during_congress",
        "party_changed_during_congress",
    ]

    summary = summary[
        front_columns
        + [
            column
            for column in summary.columns
            if column not in front_columns
        ]
    ]

    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    duplicate_members = summary.duplicated(
        subset=["bioguide_id"],
        keep=False,
    )

    bad_unity_math = summary[
        (
            summary["with_own_party_unity"]
            + summary["against_own_party_unity"]
        )
        != summary["party_unity_votes_cast"]
    ]

    bad_opportunity_math = summary[
        (
            summary["party_unity_votes_cast"]
            + summary["party_unity_not_voting"]
            + summary["party_unity_present_or_other"]
        )
        != summary["party_unity_opportunities"]
    ]

    rate_sum = (
        summary["party_unity_rate"]
        + summary["party_opposition_rate"]
    )

    bad_rates = summary[
        rate_sum.notna()
        & ((rate_sum - 1).abs() > 1e-12)
    ]

    print("\nQUALITY CHECKS")
    print("--------------")
    print(
        f"Duplicate Bioguide IDs: "
        f"{int(duplicate_members.sum()):,}"
    )
    print(
        "Party-unity cast-vote mismatches: "
        f"{len(bad_unity_math):,}"
    )
    print(
        "Party-unity opportunity mismatches: "
        f"{len(bad_opportunity_math):,}"
    )
    print(
        "Party unity/opposition rate mismatches: "
        f"{len(bad_rates):,}"
    )

    switchers = summary[
        summary["party_changed_during_congress"]
    ]

    print(
        "Members with multiple parties: "
        f"{len(switchers):,}"
    )

    if not switchers.empty:
        print("\nPARTY CHANGES")
        print("-------------")
        print(
            switchers[
                [
                    "bioguide_id",
                    "representative",
                    "state",
                    "parties_during_congress",
                    "party",
                ]
            ].to_string(index=False)
        )

    if duplicate_members.any():
        raise RuntimeError(
            "A Bioguide ID appears more than once in the "
            "member summary."
        )

    if not bad_unity_math.empty:
        raise RuntimeError(
            "Party-unity with/against counts do not reproduce "
            "party-unity votes cast."
        )

    if not bad_opportunity_math.empty:
        raise RuntimeError(
            "Party-unity participation categories do not "
            "reproduce opportunities."
        )

    if not bad_rates.empty:
        raise RuntimeError(
            "Party unity and opposition rates do not sum to 1."
        )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        output_file,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(output_file)
    print(f"Members written: {len(summary):,}")
    print(f"Columns written: {len(summary.columns):,}")

    # --------------------------------------------------------
    # Known-member diagnostic
    # --------------------------------------------------------

    fitz = summary[
        summary["bioguide_id"] == "F000466"
    ]

    print("\nFITZPATRICK CHECK")
    print("-----------------")

    if fitz.empty:
        print("F000466 not found.")
    else:
        columns = [
            "representative",
            "party",
            "state",
            "party_unity_opportunities",
            "party_unity_votes_cast",
            "party_unity_not_voting",
            "with_own_party_unity",
            "against_own_party_unity",
            "party_unity_rate",
            "party_opposition_rate",
            "party_unity_participation_rate",
        ]

        print(
            fitz[columns].to_string(index=False)
        )

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
