import json
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

CONGRESS = 119

DISTRICT_FILE = Path(
    "docs/data/districts_119.geojson"
)

VOTE_FILE = Path(
    "data/processed/members/member_vote_alignment_119.csv"
)

HISTORICAL_FILE = Path(
    "data/processed/members/member_historical_summaries_115_119.csv"
)

ALIGNMENT_DIR = Path(
    "data/processed/members"
)

OUTPUT_FILE = Path(
    "docs/data/congress_119_overview.json"
)


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


def clean_string(value):
    if pd.isna(value):
        return None
    return str(value)


def party_label(code):
    labels = {
        "R": "Republican",
        "D": "Democratic",
        "I": "Independent",
    }
    return labels.get(code, code or "Unknown")


def parse_vote_dates(series):
    return pd.to_datetime(
        series,
        format="mixed",
        dayfirst=True,
        errors="raise",
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("BipartisanCurious 119th Congress overview builder")
    print("-------------------------------------------------")

    if not DISTRICT_FILE.exists():
        raise FileNotFoundError(
            f"Missing district file: {DISTRICT_FILE}"
        )

    if not VOTE_FILE.exists():
        raise FileNotFoundError(
            f"Missing vote file: {VOTE_FILE}"
        )

    if not HISTORICAL_FILE.exists():
        raise FileNotFoundError(
            f"Missing historical summary file: {HISTORICAL_FILE}"
        )

    # --------------------------------------------------------
    # CURRENT HOUSE SNAPSHOT
    # --------------------------------------------------------


    with DISTRICT_FILE.open(encoding="utf-8") as f:
        districts = json.load(f)

    features = districts.get("features", [])

    current_rows = []

    for feature in features:
        p = feature.get("properties", {})

        current_rows.append({
            "statedistrict": p.get("statedistrict"),
            "state": p.get("state"),
            "district": p.get("district"),
            "bioguide_id": p.get("bioguide_id"),
            "name": p.get("official_name"),
            "party_code": p.get("party"),
        })

    current = pd.DataFrame(current_rows)

    occupied = current[
        current["bioguide_id"].notna()
        & current["bioguide_id"].astype(str).str.strip().ne("")
    ].copy()

    current_party_counts = (
        occupied["party_code"]
        .value_counts()
        .to_dict()
    )

    current_ids = set(
        occupied["bioguide_id"]
        .astype(str)
        .str.strip()
    )

    current_party_lookup = (
        occupied
        .set_index("bioguide_id")["party_code"]
        .to_dict()
    )

    print()
    print("CURRENT HOUSE SNAPSHOT")
    print("----------------------")
    print(f"Districts:       {len(current):,}")
    print(f"Occupied seats:  {len(occupied):,}")
    print(f"Vacant seats:    {len(current) - len(occupied):,}")
    print(
        "Democratic: "
        f"{current_party_counts.get('D', 0):,}"
    )
    print(
        "Independent: "
        f"{current_party_counts.get('I', 0):,}"
    )
    print(
        "Republican: "
        f"{current_party_counts.get('R', 0):,}"
    )

    # --------------------------------------------------------
    # 119TH-CONGRESS VOTE DATA
    # --------------------------------------------------------

    usecols = [
        "congress",
        "session",
        "roll_number",
        "action_date",
        "bioguide_id",
        "party",
        "party_code",
        "vote",
        "party_unity_vote",
        "parties_opposed",
        "parties_same_side",
        "is_major_party_member",
        "alignment",
    ]

    votes = pd.read_csv(
        VOTE_FILE,
        usecols=usecols,
        dtype={
            "bioguide_id": str,
            "party": str,
            "party_code": str,
            "vote": str,
            "alignment": str,
        },
        low_memory=False,
    )

    votes["vote_date"] = parse_vote_dates(
        votes["action_date"]
    )

    # Normalize boolean fields explicitly so strings such as
    # "False" can never be interpreted as truthy merely because
    # they are non-empty strings.
    for col in [
        "party_unity_vote",
        "parties_opposed",
        "parties_same_side",
        "is_major_party_member",
    ]:
        votes[col] = votes[col].map(
            lambda value: (
                str(value).strip().lower()
                in {"true", "1", "yes"}
                if pd.notna(value)
                else False
            )
        )

    congress_values = set(
        votes["congress"].dropna().astype(int).unique()
    )

    if congress_values != {CONGRESS}:
        raise RuntimeError(
            "Vote file contains unexpected Congress values: "
            f"{sorted(congress_values)}"
        )

    print()
    print(f"Member-vote rows loaded: {len(votes):,}")

    roll_key = [
        "congress",
        "session",
        "roll_number",
    ]

    roll_checks = (
        votes.groupby(
            roll_key,
            as_index=False,
            dropna=False,
        )
        .agg(
            vote_date=("vote_date", "first"),
            party_unity=(
                "party_unity_vote",
                "first",
            ),
            parties_opposed=(
                "parties_opposed",
                "first",
            ),
            parties_same_side=(
                "parties_same_side",
                "first",
            ),
            party_unity_values=(
                "party_unity_vote",
                "nunique",
            ),
            opposed_values=(
                "parties_opposed",
                "nunique",
            ),
            same_side_values=(
                "parties_same_side",
                "nunique",
            ),
        )
    )

    if roll_checks["party_unity_values"].max() != 1:
        raise RuntimeError(
            "party_unity_vote varies within a roll call."
        )

    if roll_checks["opposed_values"].max() != 1:
        raise RuntimeError(
            "parties_opposed varies within a roll call."
        )

    if roll_checks["same_side_values"].max() != 1:
        raise RuntimeError(
            "parties_same_side varies within a roll call."
        )

    if (
        roll_checks["parties_opposed"]
        & roll_checks["parties_same_side"]
    ).any():
        raise RuntimeError(
            "A roll call is classified as both "
            "parties-opposed and parties-same-side."
        )

    if (
        roll_checks["party_unity"]
        != roll_checks["parties_opposed"]
    ).any():
        raise RuntimeError(
            "party_unity_vote and parties_opposed disagree."
        )

    rolls = roll_checks[
        [
            "congress",
            "session",
            "roll_number",
            "vote_date",
            "parties_opposed",
            "parties_same_side",
        ]
    ].copy()

    rolls["classification"] = "other"

    rolls.loc[
        rolls["parties_same_side"],
        "classification",
    ] = "parties_same_side"

    rolls.loc[
        rolls["parties_opposed"],
        "classification",
    ] = "parties_opposed"

    total_roll_calls = len(rolls)

    roll_counts = (
        rolls["classification"]
        .value_counts()
        .to_dict()
    )

    opposed_rolls = roll_counts.get(
        "parties_opposed", 0
    )
    same_side_rolls = roll_counts.get(
        "parties_same_side", 0
    )
    other_rolls = roll_counts.get(
        "other", 0
    )

    print()
    print("ROLL CALLS")
    print("----------")
    print(f"Total:             {total_roll_calls:,}")
    print(f"Parties opposed:   {opposed_rolls:,}")
    print(f"Parties same side: {same_side_rolls:,}")
    print(f"Other:             {other_rolls:,}")
    print(
        "Opposition share:  "
        f"{opposed_rolls / total_roll_calls:.3%}"
    )

    # --------------------------------------------------------
    # SESSION AND MONTHLY ROLL-CALL SUMMARIES
    # --------------------------------------------------------

    def summarize_roll_group(group):
        counts = (
            group["classification"]
            .value_counts()
            .to_dict()
        )

        total = len(group)
        opposed = counts.get("parties_opposed", 0)

        return {
            "total": int(total),
            "parties_opposed": int(opposed),
            "parties_same_side": int(
                counts.get("parties_same_side", 0)
            ),
            "other": int(counts.get("other", 0)),
            "parties_opposed_rate": (
                float(opposed / total)
                if total
                else None
            ),
        }

    sessions = []

    print()
    print("BY SESSION")
    print("----------")

    for session, group in rolls.groupby(
        "session",
        sort=True,
    ):
        stats = summarize_roll_group(group)

        sessions.append({
            "session": clean_string(session),
            **stats,
        })

        print(
            f"{session}: "
            f"{stats['total']} total | "
            f"{stats['parties_opposed']} opposed | "
            f"{stats['parties_same_side']} same side | "
            f"{stats['other']} other"
        )

    rolls["month"] = (
        rolls["vote_date"]
        .dt.to_period("M")
        .astype(str)
    )

    monthly = []

    print()
    print("MONTHLY")
    print("-------")

    for month, group in rolls.groupby(
        "month",
        sort=True,
    ):
        stats = summarize_roll_group(group)

        monthly.append({
            "month": month,
            **stats,
        })

        print(
            f"{month}: "
            f"{stats['total']} total | "
            f"{stats['parties_opposed']} opposed | "
            f"{stats['parties_same_side']} same side | "
            f"{stats['other']} other"
        )

    # --------------------------------------------------------
    # CURRENT MEMBERS ? 119TH CONGRESS
    # --------------------------------------------------------

    current_votes = votes[
        votes["bioguide_id"].isin(current_ids)
    ].copy()

    qualifying = current_votes[
        current_votes["party_unity_vote"].eq(True)
        & current_votes["is_major_party_member"].eq(True)
    ].copy()

    def member_119_stats(party_code):
        party_ids = set(
            occupied.loc[
                occupied["party_code"].eq(party_code),
                "bioguide_id",
            ].astype(str)
        )

        x = qualifying[
            qualifying["bioguide_id"].isin(party_ids)
            & qualifying["party_code"].eq(party_code)
        ].copy()

        rows = []

        for bioguide_id in sorted(party_ids):
            g = x[x["bioguide_id"].eq(bioguide_id)]

            opportunities = len(g)

            with_party = int(
                g["alignment"]
                .eq("with_own_party")
                .sum()
            )

            against_party = int(
                g["alignment"]
                .eq("against_own_party")
                .sum()
            )

            not_voting = int(
                g["alignment"]
                .eq("not_voting")
                .sum()
            )

            present_or_other = int(
                opportunities
                - with_party
                - against_party
                - not_voting
            )

            votes_cast = with_party + against_party

            opposition_rate = (
                against_party / votes_cast
                if votes_cast
                else None
            )

            participation_rate = (
                votes_cast / opportunities
                if opportunities
                else None
            )

            rows.append({
                "bioguide_id": bioguide_id,
                "opportunities": opportunities,
                "votes_cast": votes_cast,
                "with_party": with_party,
                "against_party": against_party,
                "not_voting": not_voting,
                "present_or_other": present_or_other,
                "opposition_rate": opposition_rate,
                "participation_rate": participation_rate,
            })

        df = pd.DataFrame(rows)

        valid_opposition = df[
            "opposition_rate"
        ].dropna()

        valid_participation = df[
            "participation_rate"
        ].dropna()

        opportunities = int(
            df["opportunities"].sum()
        )
        votes_cast = int(
            df["votes_cast"].sum()
        )
        with_party = int(
            df["with_party"].sum()
        )
        against_party = int(
            df["against_party"].sum()
        )
        not_voting = int(
            df["not_voting"].sum()
        )
        present_or_other = int(
            df["present_or_other"].sum()
        )

        bands = [
            ("under_5", 0.00, 0.05),
            ("5_to_under_10", 0.05, 0.10),
            ("10_to_under_20", 0.10, 0.20),
            ("20_to_under_30", 0.20, 0.30),
            ("30_to_under_45", 0.30, 0.45),
            ("45_or_more", 0.45, None),
        ]

        band_output = {}

        for label, lower, upper in bands:
            if upper is None:
                mask = valid_opposition.ge(lower)
            else:
                mask = (
                    valid_opposition.ge(lower)
                    & valid_opposition.lt(upper)
                )

            count = int(mask.sum())

            band_output[label] = {
                "count": count,
                "share": (
                    float(count / len(valid_opposition))
                    if len(valid_opposition)
                    else None
                ),
            }

        return {
            "party": party_label(party_code),
            "members": len(party_ids),
            "opportunities": opportunities,
            "votes_cast": votes_cast,
            "with_party": with_party,
            "against_party": against_party,
            "not_voting": not_voting,
            "present_or_other": present_or_other,
            "aggregate_opposition_rate": (
                float(against_party / votes_cast)
                if votes_cast
                else None
            ),
            "aggregate_with_party_rate": (
                float(with_party / votes_cast)
                if votes_cast
                else None
            ),
            "aggregate_participation_rate": (
                float(votes_cast / opportunities)
                if opportunities
                else None
            ),
            "average_member_opposition_rate": (
                float(valid_opposition.mean())
                if len(valid_opposition)
                else None
            ),
            "median_member_opposition_rate": (
                float(valid_opposition.median())
                if len(valid_opposition)
                else None
            ),
            "median_member_participation_rate": (
                float(valid_participation.median())
                if len(valid_participation)
                else None
            ),
            "opposition_rate_bands": band_output,
            "_member_rows": rows,
        }

    member_statistics = {
        "R": member_119_stats("R"),
        "D": member_119_stats("D"),
    }

    print()
    print("CURRENT MEMBER STATISTICS")
    print("-------------------------")

    for party_code in ["R", "D"]:
        stats = member_statistics[party_code]

        print()
        print(
            "REPUBLICANS"
            if party_code == "R"
            else "DEMOCRATS"
        )
        print(
            f"Members:                  "
            f"{stats['members']:,}"
        )
        print(
            f"Qualifying opportunities: "
            f"{stats['opportunities']:,}"
        )
        print(
            f"Votes cast:               "
            f"{stats['votes_cast']:,}"
        )
        print(
            f"With party:               "
            f"{stats['with_party']:,}"
        )
        print(
            f"Against party:            "
            f"{stats['against_party']:,}"
        )
        print(
            "Aggregate opposition:     "
            f"{stats['aggregate_opposition_rate']:.2%}"
        )
        print(
            "Average member opposition:"
            f" {stats['average_member_opposition_rate']:.2%}"
        )
        print(
            "Median member opposition: "
            f"{stats['median_member_opposition_rate']:.2%}"
        )
        print(
            "Aggregate participation:  "
            f"{stats['aggregate_participation_rate']:.2%}"
        )
        print(
            "Median participation:     "
            f"{stats['median_member_participation_rate']:.2%}"
        )
        print("Opposition bands:")

        for label, band in (
            stats["opposition_rate_bands"].items()
        ):
            print(
                f"  {label:<18} "
                f"{band['count']:>3} "
                f"({band['share']:.1%})"
            )

    # --------------------------------------------------------
    # HISTORICAL SUMMARY DATA
    # --------------------------------------------------------

    historical = pd.read_csv(
        HISTORICAL_FILE,
        dtype={
            "bioguide_id": str,
            "party_code": str,
        },
    )

    historical["bioguide_id"] = (
        historical["bioguide_id"]
        .astype(str)
        .str.strip()
    )

    historical = historical[
        historical["bioguide_id"].isin(current_ids)
    ].copy()

    numeric_cols = [
        "party_unity_opportunities",
        "party_unity_votes_cast",
        "party_unity_not_voting",
        "party_unity_present_or_other",
        "with_own_party_unity",
        "against_own_party_unity",
        "party_opposition_rate",
        "party_unity_participation_rate",
    ]

    for col in numeric_cols:
        historical[col] = pd.to_numeric(
            historical[col],
            errors="coerce",
        )

    def truthy(value):
        if pd.isna(value):
            return False

        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {
            "true", "1", "yes"
        }

    historical[
        "party_changed_during_period"
    ] = historical[
        "party_changed_during_period"
    ].map(truthy)

    # --------------------------------------------------------
    # HISTORICAL CURRENT-HOUSE AGGREGATION
    # --------------------------------------------------------

    def historical_period(period_type, period_id):
        period_id = str(period_id)

        x = historical[
            historical["period_type"].eq(period_type)
            & historical["period_id"].astype(str).eq(period_id)
        ].copy()

        if x.empty:
            raise RuntimeError(
                "Historical period not found: "
                f"{period_type} / {period_id}"
            )

        period_meta = x.iloc[0]

        output = {
            "period_type": period_type,
            "period_id": period_id,
            "period_label": clean_string(
                period_meta["period_label"]
            ),
            "period_start": clean_string(
                period_meta["period_start"]
            ),
            "period_end": clean_string(
                period_meta["period_end"]
            ),
            "partial_period": truthy(
                period_meta["partial_period"]
            ),
            "parties": {},
        }

        for current_party in ["R", "D"]:
            today_ids = set(
                occupied.loc[
                    occupied["party_code"].eq(current_party),
                    "bioguide_id",
                ].astype(str)
            )

            today_total = len(today_ids)

            current_party_rows = x[
                x["bioguide_id"].isin(today_ids)
            ].copy()

            # Coverage means today's members who actually had
            # qualifying party-unity opportunities in the period,
            # regardless of what party they belonged to then.
            coverage_rows = current_party_rows[
                current_party_rows[
                    "party_unity_opportunities"
                ].fillna(0).gt(0)
            ].copy()

            coverage_ids = set(
                coverage_rows["bioguide_id"]
            )

            # The party statistic is stricter:
            # - member is in today's caucus
            # - historical row is for the same party
            # - row does not span a party change
            # - member had qualifying opportunities
            contributors = current_party_rows[
                current_party_rows[
                    "party_code"
                ].eq(current_party)
                & ~current_party_rows[
                    "party_changed_during_period"
                ]
                & current_party_rows[
                    "party_unity_opportunities"
                ].fillna(0).gt(0)
            ].copy()

            contributor_ids = set(
                contributors["bioguide_id"]
            )

            changed_rows = coverage_rows[
                coverage_rows[
                    "party_changed_during_period"
                ]
            ]

            different_party_rows = coverage_rows[
                ~coverage_rows[
                    "party_code"
                ].eq(current_party)
                & ~coverage_rows[
                    "party_changed_during_period"
                ]
            ]

            opportunities = int(
                contributors[
                    "party_unity_opportunities"
                ].sum()
            )

            votes_cast = int(
                contributors[
                    "party_unity_votes_cast"
                ].sum()
            )

            with_party = int(
                contributors[
                    "with_own_party_unity"
                ].sum()
            )

            against_party = int(
                contributors[
                    "against_own_party_unity"
                ].sum()
            )

            not_voting = int(
                contributors[
                    "party_unity_not_voting"
                ].sum()
            )

            present_or_other = int(
                contributors[
                    "party_unity_present_or_other"
                ].sum()
            )

            member_rates = (
                contributors[
                    "party_opposition_rate"
                ]
                .dropna()
            )

            participation_rates = (
                contributors[
                    "party_unity_participation_rate"
                ]
                .dropna()
            )

            output["parties"][current_party] = {
                "current_party": party_label(
                    current_party
                ),
                "current_members_today": today_total,
                "members_with_period_data": len(
                    coverage_ids
                ),
                "coverage_rate": (
                    float(
                        len(coverage_ids)
                        / today_total
                    )
                    if today_total
                    else None
                ),
                "statistic_contributors": len(
                    contributor_ids
                ),
                "statistic_contributor_rate": (
                    float(
                        len(contributor_ids)
                        / today_total
                    )
                    if today_total
                    else None
                ),
                "excluded_party_change_rows": int(
                    len(changed_rows)
                ),
                "excluded_different_party_rows": int(
                    len(different_party_rows)
                ),
                "opportunities": opportunities,
                "votes_cast": votes_cast,
                "with_party": with_party,
                "against_party": against_party,
                "not_voting": not_voting,
                "present_or_other": present_or_other,
                "aggregate_opposition_rate": (
                    float(
                        against_party / votes_cast
                    )
                    if votes_cast
                    else None
                ),
                "average_member_opposition_rate": (
                    float(member_rates.mean())
                    if len(member_rates)
                    else None
                ),
                "median_member_opposition_rate": (
                    float(member_rates.median())
                    if len(member_rates)
                    else None
                ),
                "aggregate_participation_rate": (
                    float(
                        votes_cast / opportunities
                    )
                    if opportunities
                    else None
                ),
                "median_member_participation_rate": (
                    float(
                        participation_rates.median()
                    )
                    if len(participation_rates)
                    else None
                ),
            }

        return output

    current_member_history = {
        "overall": historical_period(
            "all_available",
            "2017_present",
        ),
        "presidential_periods": {
            "trump_1": historical_period(
                "presidential",
                "trump_1",
            ),
            "biden": historical_period(
                "presidential",
                "biden",
            ),
            "trump_2": historical_period(
                "presidential",
                "trump_2",
            ),
        },
        "congresses": {
            str(congress): historical_period(
                "congress",
                str(congress),
            )
            for congress in range(115, 120)
        },
    }

    # --------------------------------------------------------
    # EACH CONGRESS AS IT EXISTED
    #
    # Unlike current_member_history, this uses every member who
    # actually served during each Congress.
    #
    # Party is evaluated at the time of each individual vote.
    # A member who switches R -> D can therefore contribute to
    # both party statistics during the same Congress.
    #
    # Independent / other-party periods are excluded because
    # there is no R/D-style "own party majority" to compare with.
    # --------------------------------------------------------

    def build_member_level_rows(source, group_cols):
        grouped = (
            source.groupby(
                group_cols,
                as_index=False,
                dropna=False,
            )
            .agg(
                opportunities=(
                    "alignment",
                    "size",
                ),
                votes_cast=(
                    "_cast_vote",
                    "sum",
                ),
                with_party=(
                    "_with_party",
                    "sum",
                ),
                against_party=(
                    "_against_party",
                    "sum",
                ),
                not_voting=(
                    "_not_voting",
                    "sum",
                ),
                present_or_other=(
                    "_present_or_other",
                    "sum",
                ),
            )
        )

        grouped = grouped[
            grouped["votes_cast"].gt(0)
        ].copy()

        grouped["opposition_rate"] = (
            grouped["against_party"]
            / grouped["votes_cast"]
        )

        grouped["participation_rate"] = (
            grouped["votes_cast"]
            / grouped["opportunities"]
        )

        return grouped


    def summarize_congress_members(rows):
        if rows.empty:
            return {
                "members": 0,
                "opportunities": 0,
                "votes_cast": 0,
                "with_party": 0,
                "against_party": 0,
                "not_voting": 0,
                "present_or_other": 0,
                "average_member_opposition_rate": None,
                "median_member_opposition_rate": None,
                "aggregate_opposition_rate": None,
                "aggregate_participation_rate": None,
            }

        opportunities = int(
            rows["opportunities"].sum()
        )

        votes_cast = int(
            rows["votes_cast"].sum()
        )

        with_party = int(
            rows["with_party"].sum()
        )

        against_party = int(
            rows["against_party"].sum()
        )

        not_voting = int(
            rows["not_voting"].sum()
        )

        present_or_other = int(
            rows["present_or_other"].sum()
        )

        if with_party + against_party != votes_cast:
            raise RuntimeError(
                "Congress member votes-cast reconciliation failed."
            )

        if (
            votes_cast
            + not_voting
            + present_or_other
            != opportunities
        ):
            raise RuntimeError(
                "Congress member opportunity reconciliation failed."
            )

        return {
            "members": int(
                rows["bioguide_id"].nunique()
            ),
            "opportunities": opportunities,
            "votes_cast": votes_cast,
            "with_party": with_party,
            "against_party": against_party,
            "not_voting": not_voting,
            "present_or_other": present_or_other,
            "average_member_opposition_rate": float(
                rows["opposition_rate"].mean()
            ),
            "median_member_opposition_rate": float(
                rows["opposition_rate"].median()
            ),
            "aggregate_opposition_rate": (
                float(
                    against_party / votes_cast
                )
                if votes_cast
                else None
            ),
            "aggregate_participation_rate": (
                float(
                    votes_cast / opportunities
                )
                if opportunities
                else None
            ),
        }


    congress_as_it_existed = {}

    print()
    print("EACH CONGRESS AS IT EXISTED")
    print("---------------------------")

    alignment_usecols = [
        "congress",
        "bioguide_id",
        "action_date",
        "party_code",
        "party_unity_vote",
        "is_major_party_member",
        "alignment",
    ]

    all_alignment_votes = []

    for congress_number in range(115, 120):

        alignment_file = (
            ALIGNMENT_DIR
            / f"member_vote_alignment_{congress_number}.csv"
        )

        if not alignment_file.exists():
            raise FileNotFoundError(
                "Missing Congress alignment file: "
                f"{alignment_file}"
            )

        congress_votes = pd.read_csv(
            alignment_file,
            usecols=alignment_usecols,
            dtype={
                "bioguide_id": str,
                "party_code": str,
                "alignment": str,
            },
            low_memory=False,
        )

        congress_values = set(
            congress_votes["congress"]
            .dropna()
            .astype(int)
            .unique()
        )

        if congress_values != {congress_number}:
            raise RuntimeError(
                f"Unexpected Congress values in "
                f"{alignment_file}: "
                f"{sorted(congress_values)}"
            )

        congress_votes["bioguide_id"] = (
            congress_votes["bioguide_id"]
            .astype(str)
            .str.strip()
        )

        congress_votes["party_code"] = (
            congress_votes["party_code"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        for col in [
            "party_unity_vote",
            "is_major_party_member",
        ]:
            congress_votes[col] = (
                congress_votes[col]
                .map(truthy)
            )

        congress_votes["vote_date"] = parse_vote_dates(
            congress_votes["action_date"]
        )

        all_alignment_votes.append(
            congress_votes.copy()
        )

        # Count major-party-opposed opportunities for people
        # who were not major-party members at that moment.
        nonmajor_opportunities = int(
            (
                congress_votes["party_unity_vote"]
                & ~congress_votes[
                    "is_major_party_member"
                ]
            ).sum()
        )

        qualifying_all = congress_votes[
            congress_votes["party_unity_vote"]
        ].copy()

        # Track affiliation changes using all rows, including
        # Independent periods.
        party_sets_all = (
            congress_votes[
                congress_votes["party_code"]
                .isin(["R", "D", "I"])
            ]
            .groupby("bioguide_id")[
                "party_code"
            ]
            .agg(
                lambda s: sorted(
                    set(s.dropna())
                )
            )
        )

        multi_affiliation = {
            member_id: parties
            for member_id, parties
            in party_sets_all.items()
            if len(parties) > 1
        }

        # Own-party statistics only make sense while the member
        # is serving as Republican or Democrat.
        qualifying = qualifying_all[
            qualifying_all[
                "is_major_party_member"
            ]
            & qualifying_all[
                "party_code"
            ].isin(["R", "D"])
        ].copy()

        qualifying["_with_party"] = (
            qualifying["alignment"]
            .eq("with_own_party")
        )

        qualifying["_against_party"] = (
            qualifying["alignment"]
            .eq("against_own_party")
        )

        qualifying["_not_voting"] = (
            qualifying["alignment"]
            .eq("not_voting")
        )

        qualifying["_cast_vote"] = (
            qualifying["_with_party"]
            | qualifying["_against_party"]
        )

        qualifying["_present_or_other"] = ~(
            qualifying["_with_party"]
            | qualifying["_against_party"]
            | qualifying["_not_voting"]
        )

        # --------------------------------------------
        # ALL MAJOR-PARTY MEMBERS
        #
        # One row per member. If a member switched R/D,
        # votes from both major-party periods remain attached
        # to that person, but each vote's own-party comparison
        # was already calculated using party at that vote.
        # --------------------------------------------

        all_member_rows = build_member_level_rows(
            qualifying,
            ["bioguide_id"],
        )

        all_stats = summarize_congress_members(
            all_member_rows
        )

        # --------------------------------------------
        # PARTY-SPECIFIC
        #
        # One row per member + party. A switcher may
        # contribute a Republican segment and a Democratic
        # segment in the same Congress.
        # --------------------------------------------

        party_member_rows = build_member_level_rows(
            qualifying,
            [
                "party_code",
                "bioguide_id",
            ],
        )

        party_stats = {}

        for party_code in ["R", "D"]:
            rows = party_member_rows[
                party_member_rows[
                    "party_code"
                ].eq(party_code)
            ].copy()

            stats = summarize_congress_members(
                rows
            )

            stats["party"] = party_label(
                party_code
            )

            party_stats[party_code] = stats

        major_party_sets = (
            qualifying.groupby(
                "bioguide_id"
            )["party_code"]
            .agg(
                lambda s: sorted(set(s))
            )
        )

        major_party_switchers = {
            member_id: parties
            for member_id, parties
            in major_party_sets.items()
            if len(parties) > 1
        }

        period = (
            current_member_history[
                "congresses"
            ][str(congress_number)]
        )

        congress_as_it_existed[
            str(congress_number)
        ] = {
            "congress": congress_number,
            "period_label": period[
                "period_label"
            ],
            "period_start": period[
                "period_start"
            ],
            "period_end": period[
                "period_end"
            ],
            "partial_period": period[
                "partial_period"
            ],

            "all_major_party_members": (
                all_stats
            ),

            "parties": party_stats,

            "unique_major_party_members": int(
                all_member_rows[
                    "bioguide_id"
                ].nunique()
            ),

            "member_party_segments": int(
                len(party_member_rows)
            ),

            "members_with_multiple_major_party_affiliations": int(
                len(major_party_switchers)
            ),

            "members_with_multiple_affiliations_in_data": int(
                len(multi_affiliation)
            ),

            "nonmajor_party_unity_opportunities_excluded": (
                nonmajor_opportunities
            ),
        }

        print()
        print(
            f"{period['period_label']}"
            + (
                " [PARTIAL]"
                if period["partial_period"]
                else ""
            )
        )

        print(
            "  All major-party members: "
            f"{all_stats['members']} members | "
            "avg opposition "
            f"{all_stats['average_member_opposition_rate']:.2%} | "
            "aggregate "
            f"{all_stats['aggregate_opposition_rate']:.2%}"
        )

        print(
            "  Republicans:            "
            f"{party_stats['R']['members']} members | "
            "avg opposition "
            f"{party_stats['R']['average_member_opposition_rate']:.2%}"
        )

        print(
            "  Democrats:              "
            f"{party_stats['D']['members']} members | "
            "avg opposition "
            f"{party_stats['D']['average_member_opposition_rate']:.2%}"
        )

        print(
            "  Member-party segments:  "
            f"{len(party_member_rows)}"
        )

        print(
            "  R/D switchers:           "
            f"{len(major_party_switchers)}"
        )

        print(
            "  Any affiliation changes: "
            f"{len(multi_affiliation)}"
        )

        print(
            "  Non-major-party qualifying "
            "opportunities excluded: "
            f"{nonmajor_opportunities}"
        )


    # --------------------------------------------------------
    # PRESIDENTIAL PERIODS AS THEY EXISTED AT THE TIME
    #
    # This differs from current_member_history:
    # it uses everyone represented in the vote-level data during
    # the presidential period, not only people serving today.
    #
    # Party affiliation is evaluated on each individual vote.
    # Independent / other-party periods are excluded from the
    # against-own-party calculation.
    # --------------------------------------------------------

    all_alignment = pd.concat(
        all_alignment_votes,
        ignore_index=True,
    )

    presidential_periods_as_it_existed = {}

    print()
    print("PRESIDENTIAL PERIODS AS THEY EXISTED")
    print("------------------------------------")

    for period_key in [
        "trump_1",
        "biden",
        "trump_2",
    ]:
        period_meta = (
            current_member_history[
                "presidential_periods"
            ][period_key]
        )

        start_date = pd.Timestamp(
            period_meta["period_start"]
        )

        end_date = pd.Timestamp(
            period_meta["period_end"]
        )

        period_votes = all_alignment[
            all_alignment["vote_date"].ge(start_date)
            & all_alignment["vote_date"].le(end_date)
        ].copy()

        if period_votes.empty:
            raise RuntimeError(
                "No vote-level data found for "
                f"{period_meta['period_label']}."
            )

        nonmajor_opportunities = int(
            (
                period_votes["party_unity_vote"]
                & ~period_votes[
                    "is_major_party_member"
                ]
            ).sum()
        )

        # All affiliations represented in the source data,
        # including Independent periods.
        party_sets_all = (
            period_votes[
                period_votes["party_code"]
                .isin(["R", "D", "I"])
            ]
            .groupby("bioguide_id")[
                "party_code"
            ]
            .agg(
                lambda s: sorted(
                    set(s.dropna())
                )
            )
        )

        multi_affiliation = {
            member_id: parties
            for member_id, parties
            in party_sets_all.items()
            if len(parties) > 1
        }

        # Own-party calculations apply only while serving as
        # Republican or Democrat on a qualifying roll call.
        qualifying = period_votes[
            period_votes["party_unity_vote"]
            & period_votes["is_major_party_member"]
            & period_votes["party_code"].isin(
                ["R", "D"]
            )
        ].copy()

        qualifying["_with_party"] = (
            qualifying["alignment"]
            .eq("with_own_party")
        )

        qualifying["_against_party"] = (
            qualifying["alignment"]
            .eq("against_own_party")
        )

        qualifying["_not_voting"] = (
            qualifying["alignment"]
            .eq("not_voting")
        )

        qualifying["_cast_vote"] = (
            qualifying["_with_party"]
            | qualifying["_against_party"]
        )

        qualifying["_present_or_other"] = ~(
            qualifying["_with_party"]
            | qualifying["_against_party"]
            | qualifying["_not_voting"]
        )

        # --------------------------------------------
        # ALL MAJOR-PARTY MEMBERS
        #
        # One row per person across the entire period.
        # If a member changes R/D affiliation, each vote's
        # own-party comparison has already been calculated
        # according to affiliation on that vote.
        # --------------------------------------------

        all_member_rows = build_member_level_rows(
            qualifying,
            ["bioguide_id"],
        )

        all_stats = summarize_congress_members(
            all_member_rows
        )

        # --------------------------------------------
        # PARTY BREAKDOWN
        #
        # One row per member + party. A switcher may
        # therefore contribute to both party averages.
        # --------------------------------------------

        party_member_rows = build_member_level_rows(
            qualifying,
            [
                "party_code",
                "bioguide_id",
            ],
        )

        party_stats = {}

        for party_code in ["R", "D"]:
            rows = party_member_rows[
                party_member_rows[
                    "party_code"
                ].eq(party_code)
            ].copy()

            stats = summarize_congress_members(
                rows
            )

            stats["party"] = party_label(
                party_code
            )

            party_stats[party_code] = stats

        major_party_sets = (
            qualifying.groupby(
                "bioguide_id"
            )["party_code"]
            .agg(
                lambda s: sorted(
                    set(s)
                )
            )
        )

        major_party_switchers = {
            member_id: parties
            for member_id, parties
            in major_party_sets.items()
            if len(parties) > 1
        }

        presidential_periods_as_it_existed[
            period_key
        ] = {
            "period_id": period_key,
            "period_label": period_meta[
                "period_label"
            ],
            "period_start": period_meta[
                "period_start"
            ],
            "period_end": period_meta[
                "period_end"
            ],
            "partial_period": period_meta[
                "partial_period"
            ],

            "all_major_party_members": (
                all_stats
            ),

            "parties": party_stats,

            "unique_major_party_members": int(
                all_member_rows[
                    "bioguide_id"
                ].nunique()
            ),

            "member_party_segments": int(
                len(party_member_rows)
            ),

            "members_with_multiple_major_party_affiliations": int(
                len(major_party_switchers)
            ),

            "members_with_multiple_affiliations_in_data": int(
                len(multi_affiliation)
            ),

            "nonmajor_party_unity_opportunities_excluded": (
                nonmajor_opportunities
            ),
        }

        suffix = (
            " [PARTIAL]"
            if period_meta["partial_period"]
            else ""
        )

        print()
        print(
            f"{period_meta['period_label']}"
            f"{suffix}"
        )

        print(
            "  All major-party members: "
            f"{all_stats['members']} members | "
            "avg opposition "
            f"{all_stats['average_member_opposition_rate']:.2%} | "
            "aggregate "
            f"{all_stats['aggregate_opposition_rate']:.2%}"
        )

        print(
            "  Republicans:            "
            f"{party_stats['R']['members']} members | "
            "avg opposition "
            f"{party_stats['R']['average_member_opposition_rate']:.2%}"
        )

        print(
            "  Democrats:              "
            f"{party_stats['D']['members']} members | "
            "avg opposition "
            f"{party_stats['D']['average_member_opposition_rate']:.2%}"
        )

        print(
            "  Unique major-party members: "
            f"{all_stats['members']}"
        )

        print(
            "  Member-party segments:     "
            f"{len(party_member_rows)}"
        )

        print(
            "  R/D switchers:              "
            f"{len(major_party_switchers)}"
        )

        print(
            "  Any affiliation changes:    "
            f"{len(multi_affiliation)}"
        )

        print(
            "  Non-major-party qualifying "
            "opportunities excluded: "
            f"{nonmajor_opportunities}"
        )


    # --------------------------------------------------------
    # CURRENT MEMBERS WITH MULTIPLE AFFILIATIONS
    # --------------------------------------------------------

    all_available = historical[
        historical["period_type"].eq("all_available")
        & historical["period_id"]
            .astype(str)
            .eq("2017_present")
    ].copy()

    changed_current = all_available[
        all_available[
            "party_changed_during_period"
        ]
    ].copy()

    party_changes = []

    for _, row in changed_current.iterrows():
        bioguide_id = row["bioguide_id"]

        evidence = historical[
            historical["bioguide_id"].eq(
                bioguide_id
            )
            & historical[
                "party_changed_during_period"
            ]
        ].copy()

        evidence = evidence[
            evidence["period_type"].isin(
                [
                    "year",
                    "congress_session",
                    "congress",
                    "presidential",
                    "all_available",
                ]
            )
        ]

        evidence_rows = []

        for _, e in evidence.iterrows():
            evidence_rows.append({
                "period_type": clean_string(
                    e["period_type"]
                ),
                "period_id": clean_string(
                    e["period_id"]
                ),
                "period_label": clean_string(
                    e["period_label"]
                ),
                "period_start": clean_string(
                    e["period_start"]
                ),
                "period_end": clean_string(
                    e["period_end"]
                ),
                "parties_during_period": clean_string(
                    e["parties_during_period"]
                ),
            })

        current_row = occupied[
            occupied["bioguide_id"].eq(
                bioguide_id
            )
        ].iloc[0]

        party_changes.append({
            "bioguide_id": bioguide_id,
            "name": clean_string(
                current_row["name"]
            ),
            "state": clean_string(
                current_row["state"]
            ),
            "district": clean_int(
                current_row["district"]
            ),
            "current_party_code": clean_string(
                current_row["party_code"]
            ),
            "current_party": party_label(
                current_row["party_code"]
            ),
            "parties_in_2017_present_data": (
                clean_string(
                    row["parties_during_period"]
                )
            ),
            "evidence": evidence_rows,
        })

    party_changes.sort(
        key=lambda row: (
            row["state"] or "",
            row["district"] or 0,
        )
    )

    # --------------------------------------------------------
    # PRINT HISTORICAL RESULTS
    # --------------------------------------------------------

    def print_history_period(period):
        print()
        suffix = (
            " [PARTIAL]"
            if period["partial_period"]
            else ""
        )

        print(
            f"{period['period_label']}{suffix}"
        )
        print(
            f"{period['period_start']} to "
            f"{period['period_end']}"
        )

        for code in ["R", "D"]:
            stats = period["parties"][code]

            label = (
                "Republicans"
                if code == "R"
                else "Democrats"
            )

            print(
                f"  {label}: "
                f"coverage "
                f"{stats['members_with_period_data']}/"
                f"{stats['current_members_today']} "
                f"({stats['coverage_rate']:.1%}) | "
                f"contributors "
                f"{stats['statistic_contributors']} | "
                f"avg opposition "
                f"{stats['average_member_opposition_rate']:.2%} | "
                f"aggregate "
                f"{stats['aggregate_opposition_rate']:.2%}"
            )

            if (
                stats["excluded_party_change_rows"]
                or stats[
                    "excluded_different_party_rows"
                ]
            ):
                print(
                    "    exclusions: "
                    f"{stats['excluded_party_change_rows']} "
                    "party-change row(s), "
                    f"{stats['excluded_different_party_rows']} "
                    "different-party row(s)"
                )

    print()
    print("CURRENT HOUSE ? HISTORICAL OVERVIEW")
    print("-----------------------------------")

    print_history_period(
        current_member_history["overall"]
    )

    print()
    print("PRESIDENTIAL PERIODS")
    print("--------------------")

    for key in ["trump_1", "biden", "trump_2"]:
        print_history_period(
            current_member_history[
                "presidential_periods"
            ][key]
        )

    print()
    print("BY CONGRESS")
    print("-----------")

    for congress in range(115, 120):
        print_history_period(
            current_member_history[
                "congresses"
            ][str(congress)]
        )

    print()
    print("CURRENT MEMBERS WITH MULTIPLE AFFILIATIONS")
    print("------------------------------------------")

    if not party_changes:
        print("None")
    else:
        for change in party_changes:
            print(
                f"{change['name']} "
                f"({change['state']}-"
                f"{change['district']}): "
                f"{change['parties_in_2017_present_data']} "
                f"| current {change['current_party']}"
            )

            narrower = [
                e
                for e in change["evidence"]
                if e["period_type"]
                in {
                    "year",
                    "congress_session",
                    "congress",
                }
            ]

            for e in narrower:
                print(
                    f"  {e['period_type']}: "
                    f"{e['period_label']} | "
                    f"{e['parties_during_period']}"
                )

    # --------------------------------------------------------
    # CURRENT MEMBER EXPORT
    # --------------------------------------------------------

    current_member_export = []

    member_119_lookup = {}

    for code in ["R", "D"]:
        for row in member_statistics[code][
            "_member_rows"
        ]:
            member_119_lookup[
                row["bioguide_id"]
            ] = row

    for _, row in occupied.sort_values(
        ["state", "district"]
    ).iterrows():
        bioguide_id = row["bioguide_id"]
        stats = member_119_lookup.get(
            bioguide_id
        )

        export_row = {
            "bioguide_id": bioguide_id,
            "name": clean_string(row["name"]),
            "state": clean_string(row["state"]),
            "district": clean_int(row["district"]),
            "party_code": clean_string(
                row["party_code"]
            ),
            "party": party_label(
                row["party_code"]
            ),
        }

        if stats is None:
            export_row.update({
                "opportunities": None,
                "votes_cast": None,
                "with_party": None,
                "against_party": None,
                "not_voting": None,
                "present_or_other": None,
                "opposition_rate": None,
                "participation_rate": None,
            })
        else:
            export_row.update({
                "opportunities": stats[
                    "opportunities"
                ],
                "votes_cast": stats[
                    "votes_cast"
                ],
                "with_party": stats[
                    "with_party"
                ],
                "against_party": stats[
                    "against_party"
                ],
                "not_voting": stats[
                    "not_voting"
                ],
                "present_or_other": stats[
                    "present_or_other"
                ],
                "opposition_rate": stats[
                    "opposition_rate"
                ],
                "participation_rate": stats[
                    "participation_rate"
                ],
            })

        current_member_export.append(
            export_row
        )

    zero_opportunity = sum(
        1
        for row in current_member_export
        if (
            row["party_code"] in {"R", "D"}
            and not row["opportunities"]
        )
    )

    print()
    print("CURRENT MEMBER EXPORT")
    print("---------------------")
    print(
        "Current occupied members: "
        f"{len(occupied):,}"
    )
    print(
        "Current members exported: "
        f"{len(current_member_export):,}"
    )
    print(
        "Current members with zero qualifying opportunities: "
        f"{zero_opportunity:,}"
    )

    # Remove private working rows before JSON export.
    for stats in member_statistics.values():
        stats.pop("_member_rows", None)

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    first_vote_date = (
        rolls["vote_date"].min().date().isoformat()
    )
    last_vote_date = (
        rolls["vote_date"].max().date().isoformat()
    )

    output = {
        "metadata": {
            "congress": CONGRESS,
            "first_vote_date": first_vote_date,
            "last_vote_date": last_vote_date,
            "current_snapshot_source": (
                "docs/data/districts_119.geojson"
            ),
            "vote_source": (
                "data/processed/members/"
                "member_vote_alignment_119.csv"
            ),
            "historical_source": (
                "data/processed/members/"
                "member_historical_summaries_115_119.csv"
            ),
        },
        "current_house": {
            "total_seats": len(current),
            "occupied_seats": len(occupied),
            "vacant_seats": (
                len(current) - len(occupied)
            ),
            "parties": {
                "Republican": int(
                    current_party_counts.get("R", 0)
                ),
                "Democratic": int(
                    current_party_counts.get("D", 0)
                ),
                "Independent": int(
                    current_party_counts.get("I", 0)
                ),
            },
        },
        "roll_calls": {
            "total": total_roll_calls,
            "parties_opposed": opposed_rolls,
            "parties_same_side": same_side_rolls,
            "other": other_rolls,
            "parties_opposed_rate": (
                opposed_rolls / total_roll_calls
            ),
        },
        "sessions": sessions,
        "monthly": monthly,
        "member_statistics": member_statistics,
        "current_member_history": (
            current_member_history
        ),
        "current_party_changes": party_changes,

        "congress_as_it_existed": (
            congress_as_it_existed
        ),

        "presidential_periods_as_it_existed": (
            presidential_periods_as_it_existed
        ),

        "current_members": current_member_export,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("OUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(
        "File size: "
        f"{OUTPUT_FILE.stat().st_size / 1024:.1f} KB"
    )
    print()
    print("BUILD PASSED")


if __name__ == "__main__":
    main()
