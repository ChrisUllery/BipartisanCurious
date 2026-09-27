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
    """Return stripped element text, or None if the element is missing/empty."""
    if element is None or element.text is None:
        return None

    value = element.text.strip()
    return value if value else None


def safe_int(value):
    """Convert a value to int when possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_party(raw_party):
    """Normalize Clerk party codes while preserving unexpected values."""
    if raw_party is None:
        return None

    raw_party = raw_party.strip()
    return PARTY_MAP.get(raw_party, raw_party)


def normalize_vote(raw_vote):
    """Normalize known Clerk vote labels while preserving unexpected values."""
    if raw_vote is None:
        return None

    raw_vote = raw_vote.strip()
    return VOTE_MAP.get(raw_vote.lower(), raw_vote)


def parse_metadata(root, source_file):
    """Extract roll-call-level metadata."""
    metadata_node = root.find("vote-metadata")

    if metadata_node is None:
        raise ValueError("XML does not contain <vote-metadata>.")

    metadata = {
        "congress": safe_int(clean_text(metadata_node.find("congress"))),
        "session": clean_text(metadata_node.find("session")),
        "roll_number": safe_int(clean_text(metadata_node.find("rollcall-num"))),
        "chamber": clean_text(metadata_node.find("chamber")),
        "majority_party_code": clean_text(metadata_node.find("majority")),
        "legislation_number": clean_text(metadata_node.find("legis-num")),
        "vote_question": clean_text(metadata_node.find("vote-question")),
        "vote_type": clean_text(metadata_node.find("vote-type")),
        "vote_result": clean_text(metadata_node.find("vote-result")),
        "action_date": clean_text(metadata_node.find("action-date")),
        "action_time": clean_text(metadata_node.find("action-time")),
        "vote_description": clean_text(metadata_node.find("vote-desc")),
        "source_file": str(source_file),
    }

    return metadata


def parse_member_votes(root, metadata):
    """Extract one row per member from <recorded-vote> elements."""
    rows = []

    for recorded_vote in root.findall(".//recorded-vote"):
        legislator = recorded_vote.find("legislator")
        vote_node = recorded_vote.find("vote")

        if legislator is None:
            continue

        row = {
            "congress": metadata["congress"],
            "session": metadata["session"],
            "roll_number": metadata["roll_number"],
            "bioguide_id": legislator.attrib.get("name-id"),
            "representative": clean_text(legislator),
            "party": normalize_party(legislator.attrib.get("party")),
            "party_code": legislator.attrib.get("party"),
            "state": legislator.attrib.get("state"),
            "role": legislator.attrib.get("role"),
            "vote": normalize_vote(clean_text(vote_node)),
        }

        rows.append(row)

    return pd.DataFrame(rows)


def parse_clerk_totals(root):
    """Extract Clerk's official party and overall vote totals."""
    rows = []

    for node in root.findall(".//vote-totals/totals-by-party"):
        rows.append(
            {
                "party": clean_text(node.find("party")),
                "yea": safe_int(clean_text(node.find("yea-total"))) or 0,
                "nay": safe_int(clean_text(node.find("nay-total"))) or 0,
                "present": safe_int(clean_text(node.find("present-total"))) or 0,
                "not_voting": safe_int(clean_text(node.find("not-voting-total"))) or 0,
            }
        )

    return pd.DataFrame(rows)


def calculate_member_totals(member_votes):
    """Calculate party totals directly from individual member records."""
    rows = []

    if member_votes.empty:
        return pd.DataFrame(
            columns=["party", "yea", "nay", "present", "not_voting"]
        )

    for party, group in member_votes.groupby("party", dropna=False):
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


def validate_totals(member_votes, clerk_totals):
    """
    Compare totals calculated from individual member records with
    the official totals supplied in the Clerk XML.
    """
    calculated = calculate_member_totals(member_votes)

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
        validation["yea_clerk"] == validation["yea_calculated"]
    )
    validation["nay_match"] = (
        validation["nay_clerk"] == validation["nay_calculated"]
    )
    validation["present_match"] = (
        validation["present_clerk"] == validation["present_calculated"]
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

    return validation


def parse_roll_call(xml_path):
    """
    Parse one Clerk House XML roll call.

    Returns:
        metadata: dict
        member_votes: pandas DataFrame
        validation: pandas DataFrame
    """
    xml_path = Path(xml_path)

    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    if root.tag != "rollcall-vote":
        raise ValueError(
            f"Unexpected XML root tag: {root.tag!r}. "
            "Expected 'rollcall-vote'."
        )

    metadata = parse_metadata(root, xml_path)
    member_votes = parse_member_votes(root, metadata)
    clerk_totals = parse_clerk_totals(root)
    validation = validate_totals(member_votes, clerk_totals)

    return metadata, member_votes, validation


if __name__ == "__main__":
    TEST_FILE = Path("data/raw/clerk_xml/2026/roll270.xml")

    metadata, member_votes, validation = parse_roll_call(TEST_FILE)

    print("\nROLL-CALL METADATA")
    print("------------------")
    for key, value in metadata.items():
        print(f"{key}: {value}")

    print("\nMEMBER VOTES")
    print("------------")
    print(member_votes.head().to_string(index=False))
    print(f"\nMember records: {len(member_votes):,}")

    print("\nVALIDATION")
    print("----------")
    print(validation.to_string(index=False))

    if validation.empty:
        print("\nWARNING: No Clerk party totals were available for validation.")
    elif validation["all_match"].all():
        print("\nPASS: All calculated party totals match the Clerk XML.")
    else:
        print("\nFAIL: At least one calculated total does not match the Clerk XML.")
