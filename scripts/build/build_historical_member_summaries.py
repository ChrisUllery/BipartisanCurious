from pathlib import Path

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

CONGRESSES = range(115, 120)

INPUT_DIR = Path("data/processed/members")

OUTPUT_FILE = (
    Path("data/processed/members")
    / "member_historical_summaries_115_119.csv"
)

LATEST_DATA_DATE = pd.Timestamp("2026-09-16")


# Presidential periods are based on the date of the roll call,
# not on Congress number.
#
# The Obama period is intentionally retained only so that votes
# from Jan. 3-19, 2017 are not incorrectly attributed to Trump.
# It is a partial period and should not be treated as a complete
# administration-level comparison.
PRESIDENTIAL_PERIODS = [
    {
        "period_id": "obama_transition",
        "period_label": "Obama (partial)",
        "start_date": pd.Timestamp("2017-01-03"),
        "end_date": pd.Timestamp("2017-01-19"),
        "partial_period": True,
    },
    {
        "period_id": "trump_1",
        "period_label": "Trump I",
        "start_date": pd.Timestamp("2017-01-20"),
        "end_date": pd.Timestamp("2021-01-19"),
        "partial_period": False,
    },
    {
        "period_id": "biden",
        "period_label": "Biden",
        "start_date": pd.Timestamp("2021-01-20"),
        "end_date": pd.Timestamp("2025-01-19"),
        "partial_period": False,
    },
    {
        "period_id": "trump_2",
        "period_label": "Trump II",
        "start_date": pd.Timestamp("2025-01-20"),
        "end_date": LATEST_DATA_DATE,
        "partial_period": True,
    },
]


# ============================================================
# HELPERS
# ============================================================

def safe_rate(numerator, denominator):
    if denominator == 0:
        return None

    return numerator / denominator


def load_alignment_data():
    frames = []

    for congress in CONGRESSES:
        path = (
            INPUT_DIR
            / f"member_vote_alignment_{congress}.csv"
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Missing required input: {path}"
            )

        df = pd.read_csv(
            path,
            low_memory=False,
        )

        df["source_congress"] = congress

        frames.append(df)

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    combined["action_date_parsed"] = pd.to_datetime(
        combined["action_date"],
        format="%d-%b-%Y",
        errors="raise",
    )

    return combined


def summarize_member(group):
    """
    Summarize one member over an arbitrary date-defined period.

    Party alignment is taken from each individual member-vote
    record. This preserves the historical party in effect at the
    time of each vote for members who changed parties.
    """

    total_roll_calls = len(group)

    yea_votes = int(
        (group["vote"] == "Yea").sum()
    )

    nay_votes = int(
        (group["vote"] == "Nay").sum()
    )

    present_votes = int(
        (group["vote"] == "Present").sum()
    )

    not_voting = int(
        (group["vote"] == "Not Voting").sum()
    )

    yea_nay_votes_cast = int(
        group["cast_yea_or_nay"].sum()
    )

    usable_alignment = group[
        group["alignment"].isin(
            [
                "with_own_party",
                "against_own_party",
            ]
        )
    ]

    with_own_party_all = int(
        (
            usable_alignment["alignment"]
            == "with_own_party"
        ).sum()
    )

    against_own_party_all = int(
        (
            usable_alignment["alignment"]
            == "against_own_party"
        ).sum()
    )

    # --------------------------------------------------------
    # Qualifying party-unity universe
    #
    # A qualifying roll call is a standard Yea/Nay roll call
    # where the Republican and Democratic voting majorities
    # take opposite positions.
    #
    # has_xx_member is deliberately NOT an exclusion.
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
            [
                "Republican",
                "Democratic",
            ]
        )
    ]

    party_unity_opportunities = len(unity)

    unity_cast = unity[
        unity["cast_yea_or_nay"]
    ]

    party_unity_votes_cast = len(unity_cast)

    party_unity_not_voting = int(
        (
            unity["alignment"]
            == "not_voting"
        ).sum()
    )

    party_unity_present_or_other = int(
        (
            unity["alignment"]
            == "present_or_other"
        ).sum()
    )

    with_own_party_unity = int(
        (
            unity_cast["alignment"]
            == "with_own_party"
        ).sum()
    )

    against_own_party_unity = int(
        (
            unity_cast["alignment"]
            == "against_own_party"
        ).sum()
    )

    parties = (
        group["party"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    parties_during_period = "|".join(parties)

    # Use the party on the member's chronologically latest
    # record as the display party for the period.
    latest_row = (
        group.sort_values(
            [
                "action_date_parsed",
                "congress",
                "roll_number",
            ]
        )
        .iloc[-1]
    )

    display_party = latest_row["party"]
    display_party_code = latest_row["party_code"]

    return pd.Series(
        {
            "representative": latest_row["representative"],
            "state": latest_row["state"],
            "party": display_party,
            "party_code": display_party_code,
            "parties_during_period": parties_during_period,
            "party_changed_during_period": len(parties) > 1,

            "first_vote_date": group[
                "action_date_parsed"
            ].min(),

            "last_vote_date": group[
                "action_date_parsed"
            ].max(),

            "total_roll_calls": total_roll_calls,

            "yea_votes": yea_votes,
            "nay_votes": nay_votes,
            "present_votes": present_votes,
            "not_voting": not_voting,
            "yea_nay_votes_cast": yea_nay_votes_cast,

            "with_own_party_all": with_own_party_all,
            "against_own_party_all": against_own_party_all,

            "party_unity_opportunities":
                party_unity_opportunities,

            "party_unity_votes_cast":
                party_unity_votes_cast,

            "party_unity_not_voting":
                party_unity_not_voting,

            "party_unity_present_or_other":
                party_unity_present_or_other,

            "with_own_party_unity":
                with_own_party_unity,

            "against_own_party_unity":
                against_own_party_unity,

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


def summarize_period(
    df,
    period_type,
    period_id,
    period_label,
    start_date,
    end_date,
    partial_period,
):
    period = df[
        (df["action_date_parsed"] >= start_date)
        & (df["action_date_parsed"] <= end_date)
    ].copy()

    if period.empty:
        raise RuntimeError(
            f"No records found for period {period_id}"
        )

    summary = (
        period.groupby(
            "bioguide_id",
            dropna=False,
            sort=True,
        )
        .apply(
            summarize_member,
            include_groups=False,
        )
        .reset_index()
    )

    summary.insert(
        0,
        "period_type",
        period_type,
    )

    summary.insert(
        1,
        "period_id",
        period_id,
    )

    summary.insert(
        2,
        "period_label",
        period_label,
    )

    summary.insert(
        3,
        "period_start",
        start_date,
    )

    summary.insert(
        4,
        "period_end",
        end_date,
    )

    summary.insert(
        5,
        "partial_period",
        partial_period,
    )

    return summary


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "BipartisanCurious historical member summary builder"
    )
    print(
        "---------------------------------------------------"
    )

    df = load_alignment_data()

    print(
        f"Member-vote rows loaded: {len(df):,}"
    )

    print(
        "Date coverage: "
        f"{df['action_date_parsed'].min().date()} "
        "through "
        f"{df['action_date_parsed'].max().date()}"
    )

    outputs = []

    # --------------------------------------------------------
    # Congress summaries
    # --------------------------------------------------------

    print("\nCONGRESS PERIODS")
    print("----------------")

    for congress in CONGRESSES:
        subset = df[
            df["congress"] == congress
        ]

        start_date = subset[
            "action_date_parsed"
        ].min()

        end_date = subset[
            "action_date_parsed"
        ].max()

        summary = summarize_period(
            df=df,
            period_type="congress",
            period_id=str(congress),
            period_label=f"{congress}th Congress",
            start_date=start_date,
            end_date=end_date,
            partial_period=(
                congress == max(CONGRESSES)
            ),
        )

        outputs.append(summary)

        print(
            f"{congress}: "
            f"{start_date.date()} to "
            f"{end_date.date()} | "
            f"{len(summary):,} members"
        )

    # --------------------------------------------------------
    # Calendar-year summaries
    # --------------------------------------------------------

    print("\nYEAR PERIODS")
    print("------------")

    years = sorted(
        df["action_date_parsed"]
        .dt.year
        .unique()
    )

    for year in years:
        subset = df[
            df["action_date_parsed"].dt.year == year
        ]

        start_date = subset[
            "action_date_parsed"
        ].min()

        end_date = subset[
            "action_date_parsed"
        ].max()

        summary = summarize_period(
            df=df,
            period_type="year",
            period_id=str(year),
            period_label=str(year),
            start_date=start_date,
            end_date=end_date,
            partial_period=(
                end_date == LATEST_DATA_DATE
            ),
        )

        outputs.append(summary)

        print(
            f"{year}: "
            f"{start_date.date()} to "
            f"{end_date.date()} | "
            f"{len(summary):,} members"
        )

    # --------------------------------------------------------
    # Congressional-session summaries
    #
    # Use the Clerk's Congress/session identity rather than
    # inferring sessions from calendar dates.
    # --------------------------------------------------------

    print("\nCONGRESSIONAL SESSION PERIODS")
    print("-----------------------------")

    session_labels = {
        "1st": "1st Session",
        "2nd": "2nd Session",
    }

    for congress in CONGRESSES:
        congress_subset = df[
            df["congress"] == congress
        ]

        sessions = (
            congress_subset["session"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

        session_order = {
            "1st": 1,
            "2nd": 2,
        }

        sessions = sorted(
            sessions,
            key=lambda value: (
                session_order.get(value, 99),
                value,
            ),
        )

        for session in sessions:
            subset = congress_subset[
                congress_subset["session"].astype(str)
                == session
            ]

            start_date = subset[
                "action_date_parsed"
            ].min()

            end_date = subset[
                "action_date_parsed"
            ].max()

            session_label = session_labels.get(
                session,
                f"{session} Session",
            )

            period_id = (
                f"{congress}_{session}"
            )

            period_label = (
                f"{congress}th Congress - "
                f"{session_label}"
            )

            summary = summarize_period(
                df=df,
                period_type="congress_session",
                period_id=period_id,
                period_label=period_label,
                start_date=start_date,
                end_date=end_date,
                partial_period=(
                    end_date == LATEST_DATA_DATE
                ),
            )

            outputs.append(summary)

            print(
                f"{period_label}: "
                f"{start_date.date()} to "
                f"{end_date.date()} | "
                f"{len(summary):,} members"
            )

    # --------------------------------------------------------
    # Presidential summaries
    # --------------------------------------------------------

    print("\nPRESIDENTIAL PERIODS")
    print("--------------------")

    for config in PRESIDENTIAL_PERIODS:
        summary = summarize_period(
            df=df,
            period_type="presidential",
            period_id=config["period_id"],
            period_label=config["period_label"],
            start_date=config["start_date"],
            end_date=config["end_date"],
            partial_period=config["partial_period"],
        )

        outputs.append(summary)

        print(
            f"{config['period_label']}: "
            f"{config['start_date'].date()} to "
            f"{config['end_date'].date()} | "
            f"{len(summary):,} members"
        )

    # --------------------------------------------------------
    # All available data
    # --------------------------------------------------------

    all_start = df[
        "action_date_parsed"
    ].min()

    all_end = df[
        "action_date_parsed"
    ].max()

    all_summary = summarize_period(
        df=df,
        period_type="all_available",
        period_id="2017_present",
        period_label="2017-present",
        start_date=all_start,
        end_date=all_end,
        partial_period=True,
    )

    outputs.append(all_summary)

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    result = pd.concat(
        outputs,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    duplicate_key = [
        "period_type",
        "period_id",
        "bioguide_id",
    ]

    duplicate_rows = result.duplicated(
        subset=duplicate_key,
        keep=False,
    )

    bad_unity_math = result[
        (
            result["with_own_party_unity"]
            + result["against_own_party_unity"]
        )
        != result["party_unity_votes_cast"]
    ]

    bad_opportunity_math = result[
        (
            result["party_unity_votes_cast"]
            + result["party_unity_not_voting"]
            + result["party_unity_present_or_other"]
        )
        != result["party_unity_opportunities"]
    ]

    rate_sum = (
        result["party_unity_rate"]
        + result["party_opposition_rate"]
    )

    bad_rates = result[
        rate_sum.notna()
        & ((rate_sum - 1).abs() > 1e-12)
    ]

    print("\nQUALITY CHECKS")
    print("--------------")

    print(
        "Duplicate member-period rows: "
        f"{int(duplicate_rows.sum()):,}"
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

    if duplicate_rows.any():
        raise RuntimeError(
            "Duplicate member-period identities detected."
        )

    if not bad_unity_math.empty:
        raise RuntimeError(
            "Party-unity with/against counts do not "
            "reproduce votes cast."
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
    # Write
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(
        f"Rows written: {len(result):,}"
    )
    print(
        f"Columns written: {len(result.columns):,}"
    )

    # --------------------------------------------------------
    # Fitzpatrick diagnostic
    # --------------------------------------------------------

    fitz = result[
        result["bioguide_id"] == "F000466"
    ]

    print("\nFITZPATRICK HISTORICAL CHECK")
    print("----------------------------")

    columns = [
        "period_type",
        "period_label",
        "party_unity_opportunities",
        "party_unity_votes_cast",
        "with_own_party_unity",
        "against_own_party_unity",
        "party_opposition_rate",
    ]

    print(
        fitz[columns].to_string(
            index=False
        )
    )

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
