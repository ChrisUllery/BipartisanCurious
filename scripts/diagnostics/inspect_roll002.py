from pathlib import Path
import xml.etree.ElementTree as ET

xml_path = Path("data/raw/clerk_xml/2025/roll002.xml")

tree = ET.parse(xml_path)
root = tree.getroot()

print("METADATA:")
metadata = root.find("vote-metadata")

if metadata is not None:
    for child in metadata:
        text = (child.text or "").strip()
        print(f"  {child.tag}: {text}")

print("\nVOTE TOTALS:")
vote_totals = root.find(".//vote-totals")

if vote_totals is None:
    print("  No vote-totals element found")
else:
    ET.indent(vote_totals, space="  ")
    print(ET.tostring(vote_totals, encoding="unicode"))

print("\nFIRST 10 RECORDED VOTES:")

for recorded_vote in root.findall(".//recorded-vote")[:10]:
    print(ET.tostring(recorded_vote, encoding="unicode").strip())
