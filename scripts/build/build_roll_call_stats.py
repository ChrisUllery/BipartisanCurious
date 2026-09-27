from pathlib import Path
import argparse

import pandas as pd


DEFAULT_CONGRESS = 119


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
            #
            # party_unity_vote is the explicit analytical name for
            # a standard Yea/Nay roll call where the Republican and
            # Democratic voting majorities take opposite positions.
            #
            # parties_opposed is retained for backward compatibility.
            "party_unity_vote": parties_opposed,
            "parties_opposed": parties_opposed,
            "parties_same_side": parties_same_side,

            # Absolute difference between Republican and Democratic
            # Yea shares among members casting Yea/Nay votes.
            #
            # 0.00 = identical party voting distributions
            # 1.00 = complete party separation
            "party_separation": (
                abs(
                    safe_share(r_yea, r_yea_nay)
                    - safe_share(d_yea, d_yea_nay)
                )
                if r_yea_nay > 0
                and d_yea_nay > 0
                else None
            ),

            # Retained for backward compatibility. This is
            # mathematically identical to party_separation.
            "major_party_yea_share_difference": (
                abs(
                    safe_share(r_yea, r_yea_nay)
                    - safe_share(d_yea, d_yea_nay)
                )
                if r_yea_nay > 0
                and d_yea_nay > 0
                else None
            ),

            # Overall House Yea/Nay margin on a 0-1 scale.
            #
            # 0.00 = evenly divided Yea/Nay vote
            # 1.00 = unanimous Yea or unanimous Nay
            "house_margin_share": (
                abs(
                    safe_share(total_yea, total_yea_nay)
                    - 0.5
                ) * 2
                if total_yea_nay > 0
                else None
            ),
        }
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build House roll-call statistics for one Congress."
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

    roll_call_file = (
        Path("data/processed/roll_calls")
        / f"roll_calls_{congress}.csv"
    )

    member_votes_file = (
        Path("data/processed/members")
        / f"member_votes_{congress}.csv"
    )

    output_file = (
        Path("data/processed/roll_calls")
        / f"roll_call_stats_{congress}.csv"
    )

    df = pd.read_csv(roll_call_file)
    member_votes = pd.read_csv(member_votes_file)

    # --------------------------------------------------------
    # Identify roll calls containing Clerk state code XX.
    #
    # These records are preserved in the canonical datasets.
    # The flag allows downstream analytical tables to exclude
    # this distinct voting universe without deleting source data.
    # --------------------------------------------------------

    roll_key = [
        "congress",
        "session",
        "roll_number",
    ]

    xx_rolls = (
        member_votes.loc[
            member_votes["state"] == "XX",
            roll_key,
        ]
        .drop_duplicates()
        .assign(has_xx_member=True)
    )

    print("BipartisanCurious full roll-call statistics builder")
    print("---------------------------------------------------")
    print(f"Congress: {congress}")
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

    # --------------------------------------------------------
    # Attach XX-member roll-call flag
    # --------------------------------------------------------

    output = output.merge(
        xx_rolls,
        on=roll_key,
        how="left",
        validate="one_to_one",
    )

    output["has_xx_member"] = (
        output["has_xx_member"]
        .fillna(False)
        .astype(bool)
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

    xx_count = int(output["has_xx_member"].sum())

    unity_mask = (
        output["party_unity_vote"]
        .fillna(False)
        .astype(bool)
    )

    unity_xx_count = int(
        (
            unity_mask
            & output["has_xx_member"]
        ).sum()
    )

    unity_no_xx_count = int(
        (
            unity_mask
            & ~output["has_xx_member"]
        ).sum()
    )

    print("\nANALYTICAL SCOPE")
    print("----------------")
    print(f"Rolls with XX members:       {xx_count:,}")
    print(
        "Party-unity rolls with XX: "
        f"{unity_xx_count:,}"
    )
    print(
        "Party-unity rolls without: "
        f"{unity_no_xx_count:,}"
    )

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

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        output_file,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(output_file)
    print(f"Rows written: {len(output):,}")
    print(f"Columns written: {len(output.columns):,}")

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
