from pathlib import Path

import pandas as pd


CONGRESS = 119

INPUT_FILE = (
    Path("data/processed/members")
    / f"member_vote_alignment_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/processed/members")
    / f"member_summaries_{CONGRESS}.csv"
)


MEMBER_KEY = [
    "bioguide_id",
    "representative",
    "party",
    "party_code",
    "state",
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
        & ~group["has_xx_member"].fillna(False).astype(bool)
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


def main():
    df = pd.read_csv(INPUT_FILE)

    print("BipartisanCurious member summary builder")
    print("----------------------------------------")
    print(f"Member-vote rows loaded: {len(df):,}")

    # Major-party legislators only for the party-unity summary.
    major = df[
        df["party"].isin(["Republican", "Democratic"])
    ].copy()

    summary = (
        major.groupby(
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

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
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
