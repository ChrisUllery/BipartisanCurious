from pathlib import Path

import pandas as pd


CONGRESS = 119

ROLL_CALL_FILE = (
    Path("data/processed/roll_calls")
    / f"roll_calls_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/processed/roll_calls")
    / f"roll_call_stats_{CONGRESS}.csv"
)


def safe_share(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def majority_position(yea, nay):
    if yea == 0 and nay == 0:
        return "No Position"
    if yea > nay:
        return "Yea"
    if nay > yea:
        return "Nay"
    return "Tie"


def build_stats(row):
    # --------------------------------------------------------
    # Overall House counts
    # --------------------------------------------------------

    total_yea = int(row["total_yea"])
    total_nay = int(row["total_nay"])
    total_present = int(row["total_present"])
    total_not_voting = int(row["total_not_voting"])

    total_yea_nay = total_yea + total_nay

    # All recorded member entries, including Present/Not Voting.
    total_members_recorded = int(row["member_records"])

    # Members who actually cast some vote rather than Not Voting.
    total_participating = (
        total_members_recorded - total_not_voting
    )

    # --------------------------------------------------------
    # Republican counts
    # --------------------------------------------------------

    r_yea = int(row["republican_yea"])
    r_nay = int(row["republican_nay"])
    r_present = int(row["republican_present"])
    r_not_voting = int(row["republican_not_voting"])

    r_yea_nay = r_yea + r_nay
    r_recorded = (
        r_yea
        + r_nay
        + r_present
        + r_not_voting
    )
    r_participating = r_recorded - r_not_voting

    # --------------------------------------------------------
    # Democratic counts
    # --------------------------------------------------------

    d_yea = int(row["democratic_yea"])
    d_nay = int(row["democratic_nay"])
    d_present = int(row["democratic_present"])
    d_not_voting = int(row["democratic_not_voting"])

    d_yea_nay = d_yea + d_nay
    d_recorded = (
        d_yea
        + d_nay
        + d_present
        + d_not_voting
    )
    d_participating = d_recorded - d_not_voting

    # --------------------------------------------------------
    # Independent counts
    # --------------------------------------------------------

    i_yea = int(row["independent_yea"])
    i_nay = int(row["independent_nay"])
    i_present = int(row["independent_present"])
    i_not_voting = int(row["independent_not_voting"])

    i_yea_nay = i_yea + i_nay
    i_recorded = (
        i_yea
        + i_nay
        + i_present
        + i_not_voting
    )
    i_participating = i_recorded - i_not_voting

    # --------------------------------------------------------
    # Standard Yea/Nay roll-call positions
    # --------------------------------------------------------

    if row["validation_type"] == "party_totals":
        house_position = majority_position(
            total_yea,
            total_nay,
        )

        r_position = majority_position(
            r_yea,
            r_nay,
        )

        d_position = majority_position(
            d_yea,
            d_nay,
        )

        parties_opposed = (
            r_position in {"Yea", "Nay"}
            and d_position in {"Yea", "Nay"}
            and r_position != d_position
        )

        parties_same_side = (
            r_position in {"Yea", "Nay"}
            and d_position in {"Yea", "Nay"}
            and r_position == d_position
        )

    else:
        house_position = None
        r_position = None
        d_position = None
        parties_opposed = False
        parties_same_side = False

    # --------------------------------------------------------
    # Return comprehensive statistics
    # --------------------------------------------------------

    return pd.Series(
        {
            # House totals
            "house_yea": total_yea,
            "house_nay": total_nay,
            "house_present": total_present,
            "house_not_voting": total_not_voting,
            "house_yea_nay_votes": total_yea_nay,
            "house_members_recorded": total_members_recorded,
            "house_participating": total_participating,

            # House shares
            "house_yea_share_of_yea_nay": safe_share(
                total_yea,
                total_yea_nay,
            ),
            "house_nay_share_of_yea_nay": safe_share(
                total_nay,
                total_yea_nay,
            ),
            "house_present_share_of_recorded": safe_share(
                total_present,
                total_members_recorded,
            ),
            "house_not_voting_share_of_recorded": safe_share(
                total_not_voting,
                total_members_recorded,
            ),
            "house_position": house_position,

            # Republican totals
            "republican_recorded": r_recorded,
            "republican_participating": r_participating,
            "republican_yea_nay_votes": r_yea_nay,
            "republican_yea_share_of_yea_nay": safe_share(
                r_yea,
                r_yea_nay,
            ),
            "republican_nay_share_of_yea_nay": safe_share(
                r_nay,
                r_yea_nay,
            ),
            "republican_present_share_of_recorded": safe_share(
                r_present,
                r_recorded,
            ),
            "republican_not_voting_share_of_recorded": safe_share(
                r_not_voting,
                r_recorded,
            ),
            "republican_position": r_position,
            "republican_majority_strength": (
                max(
                    safe_share(r_yea, r_yea_nay) or 0,
                    safe_share(r_nay, r_yea_nay) or 0,
                )
                if r_yea_nay
                else None
            ),

            # Democratic totals
            "democratic_recorded": d_recorded,
            "democratic_participating": d_participating,
            "democratic_yea_nay_votes": d_yea_nay,
            "democratic_yea_share_of_yea_nay": safe_share(
                d_yea,
                d_yea_nay,
            ),
            "democratic_nay_share_of_yea_nay": safe_share(
                d_nay,
                d_yea_nay,
            ),
            "democratic_present_share_of_recorded": safe_share(
                d_present,
                d_recorded,
            ),
            "democratic_not_voting_share_of_recorded": safe_share(
                d_not_voting,
                d_recorded,
            ),
            "democratic_position": d_position,
            "democratic_majority_strength": (
                max(
                    safe_share(d_yea, d_yea_nay) or 0,
                    safe_share(d_nay, d_yea_nay) or 0,
                )
                if d_yea_nay
                else None
            ),

            # Independent totals
            "independent_recorded": i_recorded,
            "independent_participating": i_participating,
            "independent_yea_nay_votes": i_yea_nay,
            "independent_yea_share_of_yea_nay": safe_share(
                i_yea,
                i_yea_nay,
            ),
            "independent_nay_share_of_yea_nay": safe_share(
                i_nay,
                i_yea_nay,
            ),

            # Relationship between major parties
            "parties_opposed": parties_opposed,
            "parties_same_side": parties_same_side,

            "major_party_yea_share_difference": (
                abs(
                    safe_share(r_yea, r_yea_nay)
                    - safe_share(d_yea, d_yea_nay)
                )
                if r_yea_nay > 0
                and d_yea_nay > 0
                else None
            ),
        }
    )


def main():
    df = pd.read_csv(ROLL_CALL_FILE)

    print("BipartisanCurious full roll-call statistics builder")
    print("---------------------------------------------------")
    print(f"Roll calls loaded: {len(df):,}")

    stats = df.apply(
        build_stats,
        axis=1,
    )

    output = pd.concat(
        [
            df.reset_index(drop=True),
            stats.reset_index(drop=True),
        ],
        axis=1,
    )

    # --------------------------------------------------------
    # Diagnostics
    # --------------------------------------------------------

    standard = output[
        output["validation_type"] == "party_totals"
    ]

    candidate = output[
        output["validation_type"] == "candidate_totals"
    ]

    print("\nROLL-CALL TYPES")
    print("---------------")
    print(f"Standard party-total: {len(standard):,}")
    print(f"Candidate-choice:     {len(candidate):,}")

    print("\nMAJOR-PARTY POSITIONS")
    print("---------------------")
    print(
        f"Opposed:   "
        f"{int(standard['parties_opposed'].sum()):,}"
    )
    print(
        f"Same side: "
        f"{int(standard['parties_same_side'].sum()):,}"
    )

    unresolved = standard[
        ~standard["parties_opposed"]
        & ~standard["parties_same_side"]
    ]

    print(
        f"Tie/other: "
        f"{len(unresolved):,}"
    )

    # Verify standard party-total roll calls reproduce the
    # original member-record counts. Candidate-choice votes use
    # candidate names rather than Yea/Nay and were validated
    # separately against Clerk candidate totals during ingestion.
    standard_output = output[
        output["validation_type"] == "party_totals"
    ].copy()

    bad_house_totals = standard_output[
        (
            standard_output["house_yea"]
            + standard_output["house_nay"]
            + standard_output["house_present"]
            + standard_output["house_not_voting"]
        )
        != standard_output["house_members_recorded"]
    ]

    print("\nQUALITY CHECKS")
    print("--------------")
    print(
        "Standard House count mismatches: "
        f"{len(bad_house_totals):,}"
    )
    print(
        "Candidate-choice rolls excluded from this check: "
        f"{len(candidate):,}"
    )

    if not bad_house_totals.empty:
        raise RuntimeError(
            "Standard House totals do not reproduce "
            "member-record counts."
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(f"Rows written: {len(output):,}")
    print(f"Columns written: {len(output.columns):,}")

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
