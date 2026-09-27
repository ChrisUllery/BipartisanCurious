from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd


PARTY_MAP = {
    "R": "Republican",
    "D": "Democratic",
    "I": "Independent",
}

VOTE_MAP = {
    "yea": "Yea",
    "aye": "Yea",
    "nay": "Nay",
    "no": "Nay",
    "present": "Present",
    "not voting": "Not Voting",
}


def clean_text(element):
    if element is None or element.text is None:
        return None

    value = element.text.strip()
    return value if value else None


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_party(raw_party):
    if raw_party is None:
        return None

    raw_party = raw_party.strip()
    return PARTY_MAP.get(raw_party, raw_party)


def normalize_vote(raw_vote):
    """
    Normalize standard House vote labels.

    Nonstandard choices such as Speaker candidate names are preserved
    exactly as supplied by the Clerk.
    """
    if raw_vote is None:
        return None

    raw_vote = raw_vote.strip()
    return VOTE_MAP.get(raw_vote.lower(), raw_vote)


def parse_metadata(root, source_file):
    metadata_node = root.find("vote-metadata")

    if metadata_node is None:
        raise ValueError("XML does not contain <vote-metadata>.")

    return {
        "congress": safe_int(clean_text(metadata_node.find("congress"))),
        "session": clean_text(metadata_node.find("session")),
        "roll_number": safe_int(
            clean_text(metadata_node.find("rollcall-num"))
        ),
        "chamber": clean_text(metadata_node.find("chamber")),
        "majority_party_code": clean_text(
            metadata_node.find("majority")
        ),
        "legislation_number": clean_text(
            metadata_node.find("legis-num")
        ),
        "vote_question": clean_text(
            metadata_node.find("vote-question")
        ),
        "vote_type": clean_text(
            metadata_node.find("vote-type")
        ),
        "vote_result": clean_text(
            metadata_node.find("vote-result")
        ),
        "action_date": clean_text(
            metadata_node.find("action-date")
        ),
        "action_time": clean_text(
            metadata_node.find("action-time")
        ),
        "vote_description": clean_text(
            metadata_node.find("vote-desc")
        ),
        "source_file": str(source_file),
    }


def parse_member_votes(root, metadata):
    rows = []

    for recorded_vote in root.findall(".//recorded-vote"):
        legislator = recorded_vote.find("legislator")
        vote_node = recorded_vote.find("vote")

        if legislator is None:
            continue

        rows.append(
            {
                "congress": metadata["congress"],
                "session": metadata["session"],
                "roll_number": metadata["roll_number"],
                "bioguide_id": legislator.attrib.get("name-id"),
                "representative": clean_text(legislator),
                "party": normalize_party(
                    legislator.attrib.get("party")
                ),
                "party_code": legislator.attrib.get("party"),
                "state": legislator.attrib.get("state"),
                "role": legislator.attrib.get("role"),
                "vote": normalize_vote(
                    clean_text(vote_node)
                ),
            }
        )

    return pd.DataFrame(rows)


def parse_party_totals(root):
    rows = []

    for node in root.findall(
        ".//vote-totals/totals-by-party"
    ):
        rows.append(
            {
                "party": clean_text(node.find("party")),
                "yea": safe_int(
                    clean_text(node.find("yea-total"))
                ) or 0,
                "nay": safe_int(
                    clean_text(node.find("nay-total"))
                ) or 0,
                "present": safe_int(
                    clean_text(node.find("present-total"))
                ) or 0,
                "not_voting": safe_int(
                    clean_text(node.find("not-voting-total"))
                ) or 0,
            }
        )

    return pd.DataFrame(rows)


def parse_candidate_totals(root):
    rows = []

    for node in root.findall(
        ".//vote-totals/totals-by-candidate"
    ):
        rows.append(
            {
                "choice": clean_text(node.find("candidate")),
                "clerk_total": safe_int(
                    clean_text(node.find("candidate-total"))
                ) or 0,
            }
        )

    return pd.DataFrame(rows)


def calculate_party_totals(member_votes):
    rows = []

    if member_votes.empty:
        return pd.DataFrame(
            columns=[
                "party",
                "yea",
                "nay",
                "present",
                "not_voting",
            ]
        )

    for party, group in member_votes.groupby(
        "party",
        dropna=False,
    ):
        counts = Counter(group["vote"])

        rows.append(
            {
                "party": party,
                "yea": counts.get("Yea", 0),
                "nay": counts.get("Nay", 0),
                "present": counts.get("Present", 0),
                "not_voting": counts.get("Not Voting", 0),
            }
        )

    return pd.DataFrame(rows)


def validate_party_totals(member_votes, clerk_totals):
    calculated = calculate_party_totals(member_votes)

    validation = clerk_totals.merge(
        calculated,
        on="party",
        how="outer",
        suffixes=("_clerk", "_calculated"),
    ).fillna(0)

    numeric_columns = [
        "yea_clerk",
        "nay_clerk",
        "present_clerk",
        "not_voting_clerk",
        "yea_calculated",
        "nay_calculated",
        "present_calculated",
        "not_voting_calculated",
    ]

    for column in numeric_columns:
        validation[column] = validation[column].astype(int)

    validation["yea_match"] = (
        validation["yea_clerk"]
        == validation["yea_calculated"]
    )
    validation["nay_match"] = (
        validation["nay_clerk"]
        == validation["nay_calculated"]
    )
    validation["present_match"] = (
        validation["present_clerk"]
        == validation["present_calculated"]
    )
    validation["not_voting_match"] = (
        validation["not_voting_clerk"]
        == validation["not_voting_calculated"]
    )

    validation["all_match"] = validation[
        [
            "yea_match",
            "nay_match",
            "present_match",
            "not_voting_match",
        ]
    ].all(axis=1)

    validation.insert(0, "validation_type", "party_totals")

    return validation


def validate_candidate_totals(member_votes, clerk_totals):
    calculated = (
        member_votes["vote"]
        .value_counts(dropna=False)
        .rename_axis("choice")
        .reset_index(name="calculated_total")
    )

    validation = clerk_totals.merge(
        calculated,
        on="choice",
        how="outer",
    ).fillna(0)

    validation["clerk_total"] = (
        validation["clerk_total"].astype(int)
    )
    validation["calculated_total"] = (
        validation["calculated_total"].astype(int)
    )

    validation["all_match"] = (
        validation["clerk_total"]
        == validation["calculated_total"]
    )

    validation.insert(
        0,
        "validation_type",
        "candidate_totals",
    )

    return validation


def validate_totals(root, member_votes):
    """
    Detect the Clerk total schema and validate accordingly.

    Standard roll calls use totals-by-party.
    Candidate-choice votes, such as Speaker elections, use
    totals-by-candidate.
    """
    party_totals = parse_party_totals(root)

    if not party_totals.empty:
        return validate_party_totals(
            member_votes,
            party_totals,
        )

    candidate_totals = parse_candidate_totals(root)

    if not candidate_totals.empty:
        return validate_candidate_totals(
            member_votes,
            candidate_totals,
        )

    raise ValueError(
        "Unsupported or missing <vote-totals> structure."
    )


def parse_roll_call(xml_path):
    xml_path = Path(xml_path)

    if not xml_path.exists():
        raise FileNotFoundError(
            f"XML file not found: {xml_path}"
        )

    tree = ET.parse(xml_path)
    root = tree.getroot()

    if root.tag != "rollcall-vote":
        raise ValueError(
            f"Unexpected XML root tag: {root.tag!r}. "
            "Expected 'rollcall-vote'."
        )

    metadata = parse_metadata(root, xml_path)
    member_votes = parse_member_votes(root, metadata)
    validation = validate_totals(root, member_votes)

    return metadata, member_votes, validation


if __name__ == "__main__":
    TEST_FILES = [
        Path("data/raw/clerk_xml/2025/roll002.xml"),
        Path("data/raw/clerk_xml/2026/roll270.xml"),
    ]

    for test_file in TEST_FILES:
        print("\n" + "=" * 70)
        print(test_file)
        print("=" * 70)

        metadata, member_votes, validation = parse_roll_call(
            test_file
        )

        print(
            f"Question: {metadata['vote_question']}"
        )
        print(
            f"Member records: {len(member_votes):,}"
        )

        print("\nFirst five votes:")
        print(
            member_votes[
                [
                    "bioguide_id",
                    "representative",
                    "party",
                    "vote",
                ]
            ]
            .head()
            .to_string(index=False)
        )

        print("\nValidation:")
        print(validation.to_string(index=False))

        if validation["all_match"].all():
            print("\nPASS")
        else:
            print("\nFAIL")
