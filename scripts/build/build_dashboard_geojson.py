from pathlib import Path
import json

import pandas as pd


CONGRESS = 119

GEOJSON_FILE = Path(
    "data/raw/census/cd119_500k.geojson"
)

MEMBERS_FILE = (
    Path("data/processed/dashboard")
    / f"members_current_{CONGRESS}.csv"
)

OUTPUT_FILE = (
    Path("data/processed/dashboard")
    / f"districts_{CONGRESS}.geojson"
)


FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR",
    "06": "CA", "08": "CO", "09": "CT", "10": "DE",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID",
    "17": "IL", "18": "IN", "19": "IA", "20": "KS",
    "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV",
    "33": "NH", "34": "NJ", "35": "NM", "36": "NY",
    "37": "NC", "38": "ND", "39": "OH", "40": "OK",
    "41": "OR", "42": "PA", "44": "RI", "45": "SC",
    "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
}


def clean_value(value):
    """
    Convert pandas/numpy values into JSON-safe native values.
    Missing values become None.
    """

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def main():
    with GEOJSON_FILE.open(encoding="utf-8") as f:
        source = json.load(f)

    # --------------------------------------------------------
    # Validate source geography before doing any joins.
    # --------------------------------------------------------

    source_features = source.get("features", [])

    if len(source_features) != 441:
        raise RuntimeError(
            "Expected 441 Census congressional-district "
            f"features, found {len(source_features)}."
        )

    missing_geometry = []
    invalid_geometry = []

    for feature in source_features:
        props = feature.get("properties", {})
        geoid = str(props.get("GEOID", "UNKNOWN"))

        geometry = feature.get("geometry")

        if (
            not geometry
            or not geometry.get("coordinates")
        ):
            missing_geometry.append(geoid)
            continue

        if geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            invalid_geometry.append(
                (
                    geoid,
                    geometry.get("type"),
                )
            )

    if missing_geometry:
        raise RuntimeError(
            "Census source contains "
            f"{len(missing_geometry)} features with "
            "missing/empty geometry. Examples: "
            + ", ".join(missing_geometry[:10])
        )

    if invalid_geometry:
        raise RuntimeError(
            "Census source contains unexpected geometry "
            f"types. Examples: {invalid_geometry[:10]}"
        )

    members = pd.read_csv(
        MEMBERS_FILE,
        dtype={
            "statedistrict": str,
            "bioguide_id": str,
        },
    )

    print("BipartisanCurious dashboard geography builder")
    print("---------------------------------------------")
    print(f"Source geography features: {len(source['features']):,}")
    print(f"Dashboard district rows:   {len(members):,}")

    member_lookup = (
        members
        .set_index("statedistrict")
        .to_dict(orient="index")
    )

    output_features = []
    excluded_features = []

    for feature in source["features"]:
        props = feature["properties"]

        geoid = str(props["GEOID"]).zfill(4)

        state_fips = geoid[:2]
        district_code = geoid[2:]

        state = FIPS_TO_STATE.get(state_fips)

        # Exclude DC/territories/non-state constituencies.
        if state is None:
            excluded_features.append({
                "GEOID": geoid,
                "CD119": props.get("CD119"),
            })
            continue

        statedistrict = f"{state}{district_code}"

        member = member_lookup.get(statedistrict)

        if member is None:
            raise RuntimeError(
                f"No dashboard member row for {statedistrict} "
                f"(Census GEOID {geoid})."
            )

        # Keep the geography properties compact and add the
        # dashboard/member values needed by the front end.
        dashboard_props = {
            "statedistrict": statedistrict,
            "state": state,
            "district": int(district_code),

            "bioguide_id": clean_value(
                member.get("bioguide_id")
            ),
            "official_name": clean_value(
                member.get("official_name")
            ),
            "party": clean_value(
                member.get("party_current")
            ),

            "party_unity_opportunities": clean_value(
                member.get("party_unity_opportunities")
            ),
            "party_unity_votes_cast": clean_value(
                member.get("party_unity_votes_cast")
            ),
            "party_unity_not_voting": clean_value(
                member.get("party_unity_not_voting")
            ),
            "with_own_party_unity": clean_value(
                member.get("with_own_party_unity")
            ),
            "against_own_party_unity": clean_value(
                member.get("against_own_party_unity")
            ),
            "party_unity_rate": clean_value(
                member.get("party_unity_rate")
            ),
            "party_opposition_rate": clean_value(
                member.get("party_opposition_rate")
            ),
            "party_unity_participation_rate": clean_value(
                member.get("party_unity_participation_rate")
            ),
        }

        output_features.append({
            "type": "Feature",
            "properties": dashboard_props,
            "geometry": feature["geometry"],
        })

    output = {
        "type": "FeatureCollection",
        "features": output_features,
    }

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    output_codes = [
        f["properties"]["statedistrict"]
        for f in output_features
    ]

    member_codes = set(members["statedistrict"])
    geo_codes = set(output_codes)

    missing_geometry = sorted(member_codes - geo_codes)
    extra_geometry = sorted(geo_codes - member_codes)

    print("\nGEOGRAPHY CHECK")
    print("---------------")
    print(f"State district features:  {len(output_features):,}")
    print(f"Unique district codes:    {len(geo_codes):,}")
    print(f"Excluded non-state:       {len(excluded_features):,}")
    print(f"Members missing geometry: {len(missing_geometry):,}")
    print(f"Geometry missing member:  {len(extra_geometry):,}")

    if excluded_features:
        print("\nEXCLUDED FEATURES")
        print("-----------------")
        for row in excluded_features:
            print(
                f"GEOID {row['GEOID']} "
                f"| CD119 {row['CD119']}"
            )

    if len(output_features) != 435:
        raise RuntimeError(
            f"Expected 435 state district features, "
            f"found {len(output_features)}."
        )

    if len(geo_codes) != 435:
        raise RuntimeError(
            "State district geography contains duplicate codes."
        )

    if missing_geometry:
        raise RuntimeError(
            "Dashboard districts missing Census geometry: "
            + ", ".join(missing_geometry)
        )

    if extra_geometry:
        raise RuntimeError(
            "Census districts missing dashboard member rows: "
            + ", ".join(extra_geometry)
        )

    # --------------------------------------------------------
    # Fitzpatrick check
    # --------------------------------------------------------

    fitz = next(
        (
            f for f in output_features
            if f["properties"]["statedistrict"] == "PA01"
        ),
        None,
    )

    print("\nFITZPATRICK CHECK")
    print("-----------------")

    if fitz is None:
        raise RuntimeError("PA01 not found in dashboard geography.")

    for key, value in fitz["properties"].items():
        print(f"{key}: {value}")

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    print("\nOUTPUT")
    print("------")
    print(OUTPUT_FILE)
    print(f"Features written: {len(output_features):,}")
    print(
        f"File size: "
        f"{OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print("\nBUILD PASSED")


if __name__ == "__main__":
    main()
