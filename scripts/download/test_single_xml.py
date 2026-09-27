from pathlib import Path
import xml.etree.ElementTree as ET

import requests


YEAR = 2026
ROLL_NUMBER = 270

URL = f"https://clerk.house.gov/evs/{YEAR}/roll{ROLL_NUMBER}.xml"

OUTPUT_DIR = Path("data/raw/clerk_xml") / str(YEAR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / f"roll{ROLL_NUMBER:03d}.xml"


print(f"Downloading:")
print(URL)

response = requests.get(URL, timeout=30)
response.raise_for_status()

OUTPUT_FILE.write_bytes(response.content)

print(f"\nSaved:")
print(OUTPUT_FILE)

print(f"\nDownloaded {len(response.content):,} bytes")


# --------------------------------------------------
# Parse XML
# --------------------------------------------------

tree = ET.parse(OUTPUT_FILE)
root = tree.getroot()

print("\nROOT TAG")
print(root.tag)

print("\nTOP-LEVEL ELEMENTS")
for child in root:
    print(f"  {child.tag}")


# --------------------------------------------------
# Inspect vote metadata
# --------------------------------------------------

metadata = root.find("vote-metadata")

print("\nVOTE METADATA")

if metadata is None:
    print("  vote-metadata element not found")
else:
    for child in metadata:
        text = (child.text or "").strip()
        print(f"  {child.tag}: {text}")

print("\nVOTE TOTALS STRUCTURE")

vote_totals = root.find(".//vote-totals")

if vote_totals is None:
    print("  vote-totals element not found")
else:
    ET.indent(vote_totals, space="  ")
    print(ET.tostring(vote_totals, encoding="unicode"))
# --------------------------------------------------
# Inspect first five member votes
# --------------------------------------------------

print("\nFIRST FIVE MEMBER VOTES")

recorded_votes = root.findall(".//recorded-vote")

for rv in recorded_votes[:5]:
    legislator = rv.find("legislator")
    vote = rv.find("vote")

    if legislator is None:
        continue

    print(
        {
            "name": (legislator.text or "").strip(),
            "name_id": legislator.attrib.get("name-id"),
            "party": legislator.attrib.get("party"),
            "state": legislator.attrib.get("state"),
            "role": legislator.attrib.get("role"),
            "vote": (vote.text or "").strip() if vote is not None else None,
        }
    )

print(f"\nTOTAL RECORDED-VOTE ELEMENTS: {len(recorded_votes)}")