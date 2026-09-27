from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd


CONGRESS = 119

MEMBERDATA_FILE = Path("data/raw/MemberData.xml")

SUMMARY_FILE = (
    Path("data/processed/members")
    / f"member_summaries_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/processed/dashboard")
    / f"members_current_{CONGRESS}.csv"
)


STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
}


def main():
    root = ET.parse(MEMBERDATA_FILE).getroot()

    congress = root.findtext("./title-info/congress-num")
    publish_date = root.attrib.get("publish-date")

    print("BipartisanCurious current-member builder")
    print("----------------------------------------")
    print(f"MemberData Congress: {congress}")
    print(f"MemberData published: {publish_date}")

    if str(congress) != str(CONGRESS):
        raise RuntimeError(
            f"Expected Congress {CONGRESS}, found {congress}."
        )

    rows = []

    for member in root.findall("./members/member"):
        info = member.find("member-info")

        if info is None:
            continue

        state_elem = info.find("state")

        state = (
            state_elem.attrib.get("postal-code")
            if state_elem is not None
            else None
        )

        if state not in STATES:
            continue

        statedistrict = member.findtext("statedistrict")

        if not statedistrict:
            raise RuntimeError(
                "State member missing statedistrict."
            )

        district_code = statedistrict[-2:]

        try:
            district_number = int(district_code)
        except ValueError:
            raise RuntimeError(
                f"Could not parse district from {statedistrict}."
            )

        rows.append({
            "congress": CONGRESS,
            "roster_publish_date": publish_date,
            "statedistrict": statedistrict,
            "state": state,
            "district": district_number,
            "bioguide_id": info.findtext("bioguideID"),
            "official_name": info.findtext("official-name"),
            "party_current": info.findtext("party"),
            "caucus_current": info.findtext("caucus"),
            "elected_date": (
                info.find("elected-date").attrib.get("date")
                if info.find("elected-date") is not None
                else None
            ),
            "sworn_date": (
                info.find("sworn-date").attrib.get("date")
                if info.find("sworn-date") is not None
                else None
            ),
        })

    roster = pd.DataFrame(rows)

    print("\nROSTER CHECK")
    print("------------")
    print(f"State-seat records:        {len(roster):,}")
    print(
        "Unique state/districts:   "
        f"{roster['statedistrict'].nunique():,}"
    )
    occupied = roster[
        roster["bioguide_id"].fillna("").str.strip() != ""
    ].copy()

    vacant = roster[
        roster["bioguide_id"].fillna("").str.strip() == ""
    ].copy()

    print(
        "Occupied seats:           "
        f"{len(occupied):,}"
    )
    print(
        "Vacant seats:             "
        f"{len(vacant):,}"
    )
    print(
        "Unique occupied Bioguides:"
        f" {occupied['bioguide_id'].nunique():,}"
    )

    if len(roster) != 435:
        raise RuntimeError(
            f"Expected 435 state-seat records, found {len(roster)}."
        )

    if roster["statedistrict"].nunique() != 435:
        raise RuntimeError(
            "Current roster does not contain 435 unique districts."
        )

    if occupied["bioguide_id"].duplicated().any():
        raise RuntimeError(
            "Duplicate Bioguide IDs found among occupied seats."
        )

    if not vacant.empty:
        print("\nVACANT SEATS")
        print("------------")
        print(
            vacant[
                [
                    "statedistrict",
                    "state",
                    "district",
                ]
            ].to_string(index=False)
        )

    # --------------------------------------------------------
    # Join current roster to voting summaries
    # --------------------------------------------------------

    summaries = pd.read_csv(SUMMARY_FILE)

    # Join voting summaries only to occupied seats.
    #
    # Vacancy records intentionally have blank Bioguide IDs, so
    # they cannot participate in a one-to-one member join. They
    # are added back afterward so the dashboard retains all 435
    # congressional districts.

    occupied_dashboard = occupied.merge(
        summaries,
        on="bioguide_id",
        how="left",
        validate="one_to_one",
        indicator=True,
        suffixes=("_current", "_summary"),
    )

    # Give vacancy rows the same columns as the joined table.
    vacant_dashboard = vacant.reindex(
        columns=occupied_dashboard.columns
    ).copy()

    vacant_dashboard["_merge"] = "left_only"

    dashboard = pd.concat(
        [
            occupied_dashboard,
            vacant_dashboard,
        ],
        ignore_index=True,
    )

    dashboard = dashboard.sort_values(
        ["state_current", "district"]
    ).reset_index(drop=True)

    matched = int((dashboard["_merge"] == "both").sum())
    unmatched = dashboard[dashboard["_merge"] != "both"].copy()

    print("\nSUMMARY JOIN")
    print("------------")
    print(f"Current members matched:   {matched:,}")
    print(f"Current members unmatched: {len(unmatched):,}")

    if not unmatched.empty:
        print("\nUNMATCHED CURRENT MEMBERS")
        print("-------------------------")
        print(
            unmatched[
                [
                    "statedistrict",
                    "bioguide_id",
                    "official_name",
                    "party_current",
                    "sworn_date",
                ]
            ].to_string(index=False)
        )

    dashboard = dashboard.drop(columns="_merge")

    # --------------------------------------------------------
    # Final checks
    # --------------------------------------------------------

    fitz = dashboard[
        dashboard["bioguide_id"] == "F000466"
    ]

    print("\nFITZPATRICK CHECK")
    print("-----------------")

    if fitz.empty:
        print("Fitzpatrick not found.")
    else:
        columns = [
            "statedistrict",
            "official_name",
            "party_current",
            "party_unity_opportunities",
            "party_unity_votes_cast",
            "against_own_party_unity",
            "party_opposition_rate",
        ]

        print(
            fitz[columns]
            .to_string(index=False)
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dashboard.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(f"Rows written: {len(dashboard):,}")
    print(f"Columns written: {len(dashboard.columns):,}")

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
