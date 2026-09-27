from pathlib import Path

import pandas as pd


CONGRESS = 119

INPUT_FILE = (
    Path("data/processed/roll_calls")
    / f"roll_calls_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/diagnostics")
    / f"party_division_profile_{CONGRESS}.csv"
)


def majority_position(yea, nay):
    if yea > nay:
        return "Yea"
    if nay > yea:
        return "Nay"
    return "Tie"


def calculate_profile(row):
    r_yea = row["republican_yea"]
    r_nay = row["republican_nay"]
    d_yea = row["democratic_yea"]
    d_nay = row["democratic_nay"]

    r_voting = r_yea + r_nay
    d_voting = d_yea + d_nay

    r_yea_share = (
        r_yea / r_voting
        if r_voting > 0
        else None
    )

    d_yea_share = (
        d_yea / d_voting
        if d_voting > 0
        else None
    )

    r_position = majority_position(r_yea, r_nay)
    d_position = majority_position(d_yea, d_nay)

    opposite = (
        r_position in {"Yea", "Nay"}
        and d_position in {"Yea", "Nay"}
        and r_position != d_position
    )

    r_majority_strength = (
        max(r_yea, r_nay) / r_voting
        if r_voting > 0
        else None
    )

    d_majority_strength = (
        max(d_yea, d_nay) / d_voting
        if d_voting > 0
        else None
    )

    party_difference = (
        abs(r_yea_share - d_yea_share)
        if r_yea_share is not None
        and d_yea_share is not None
        else None
    )

    return pd.Series(
        {
            "republican_yea_nay_votes": r_voting,
            "democratic_yea_nay_votes": d_voting,
            "republican_yea_share": r_yea_share,
            "democratic_yea_share": d_yea_share,
            "republican_position": r_position,
            "democratic_position": d_position,
            "opposite_party_majorities": opposite,
            "republican_majority_strength": r_majority_strength,
            "democratic_majority_strength": d_majority_strength,
            "party_difference": party_difference,
        }
    )


def main():
    df = pd.read_csv(INPUT_FILE)

    print("BipartisanCurious party-division profiler")
    print("-----------------------------------------")
    print(f"Roll calls loaded: {len(df):,}")

    print("\nVALIDATION TYPES")
    print("----------------")
    print(
        df["validation_type"]
        .value_counts(dropna=False)
        .to_string()
    )

    ordinary = df[
        df["validation_type"] == "party_totals"
    ].copy()

    candidate = df[
        df["validation_type"] == "candidate_totals"
    ].copy()

    profile = ordinary.apply(
        calculate_profile,
        axis=1,
    )

    ordinary = pd.concat(
        [
            ordinary.reset_index(drop=True),
            profile.reset_index(drop=True),
        ],
        axis=1,
    )

    opposite = ordinary[
        ordinary["opposite_party_majorities"]
    ].copy()

    print("\nBASIC COUNTS")
    print("------------")
    print(f"Ordinary party-total votes: {len(ordinary):,}")
    print(f"Candidate-choice votes:     {len(candidate):,}")
    print(
        "Opposite party majorities: "
        f"{len(opposite):,}"
    )

    same_side = ordinary[
        ~ordinary["opposite_party_majorities"]
    ]

    print(
        "Not opposite majorities:   "
        f"{len(same_side):,}"
    )

    print("\nOPPOSING-MAJORITY STRENGTH")
    print("--------------------------")
    print(
        "For votes where Democrats and Republicans "
        "have opposite majority positions:"
    )

    thresholds = [
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
    ]

    for threshold in thresholds:
        count = (
            (
                opposite["republican_majority_strength"]
                >= threshold
            )
            & (
                opposite["democratic_majority_strength"]
                >= threshold
            )
        ).sum()

        pct = (
            count / len(opposite) * 100
            if len(opposite)
            else 0
        )

        print(
            f"Both parties >= {threshold:.0%}: "
            f"{count:>3,} "
            f"({pct:5.1f}% of opposite-majority votes)"
        )

    print("\nPARTY-DIFFERENCE DISTRIBUTION")
    print("-----------------------------")

    difference_thresholds = [
        0.10,
        0.20,
        0.30,
        0.40,
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
    ]

    for threshold in difference_thresholds:
        count = (
            opposite["party_difference"]
            >= threshold
        ).sum()

        pct = (
            count / len(opposite) * 100
            if len(opposite)
            else 0
        )

        print(
            f"Difference >= {threshold:.0%}: "
            f"{count:>3,} "
            f"({pct:5.1f}%)"
        )

    print("\nMAJORITY-STRENGTH SUMMARY")
    print("-------------------------")

    if not opposite.empty:
        summary = opposite[
            [
                "republican_majority_strength",
                "democratic_majority_strength",
                "party_difference",
            ]
        ].describe(
            percentiles=[
                0.10,
                0.25,
                0.50,
                0.75,
                0.90,
            ]
        )

        print(summary.to_string())

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ordinary.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()
