"""
Adds committee assignments to data/legislators.json and writes data/committees.json.

Sources (public lists, 57th Legislature, 2nd Regular Session):
  Senate standing committees   azsenate.gov/SenateList/2026 COMMITTEE ASSIGNMENTS.pdf   (revised #2, 3/13/2026)
  House standing committees    azhouse.gov/HouseLists/57TH 2R STANDING COMMITTEE ASSIGNMENTS - BY COMMITTEE (REVISED 3.20.26).PDF
  JLBC / JLAC                  azsenate.gov/SenateList/2026 STATUTORY COMMITTEES.pdf   (1/28/2026)

The House list predates Rep. Marshall's April resignation, so his seats are
dropped and Rep. Allen (his appointed successor) has no assignments listed.
Re-check against azleg.gov before relying on any single assignment.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "legislators.json"

SOURCES = {
    "S": "https://www.azsenate.gov/SenateList/2026%20COMMITTEE%20ASSIGNMENTS.pdf",
    "H": "https://azhouse.gov/HouseLists/57TH%202R%20STANDING%20COMMITTEE%20ASSIGNMENTS%20-%20BY%20COMMITTEE%20(REVISED%203.20.26).PDF",
    "J": "https://www.azsenate.gov/SenateList/2026%20STATUTORY%20COMMITTEES.pdf",
}

# Committees AZ SBDC cares most about for the state line-item and ESOP work.
PRIORITY = {
    "S:Appropriations, Transportation and Technology": "budget",
    "S:Finance": "tax",
    "S:Regulatory Affairs and Government Efficiency": "regulatory",
    "H:Appropriations": "budget",
    "H:Commerce": "commerce",
    "H:Ways & Means": "tax",
    "H:Rural Economic Development": "economic development",
    "H:Regulatory Oversight": "regulatory",
    "J:Joint Legislative Budget Committee": "budget",
}

# (committee, chair, vice chair, other members)  — names as printed
SENATE = [
    ("Appropriations, Transportation and Technology", "David C. Farnsworth", "John Kavanagh",
     ["Lela Alston", "Hildy Angius", 'Denise "Mitzi" Epstein', "Brian Fernandez", "Mark Finchem", "Lauren Kuby", 'Venden "Vince" Leach', "Carine Werner"]),
    ("Director Nominations", "Jake Hoffman", 'Thomas "T.J." Shope', ["Flavio Bravo", "John Kavanagh", "Analise Ortiz"]),
    ("Education", "Hildy Angius", "Carine Werner", ["Flavio Bravo", "Eva Diaz", 'Timothy "Tim" Dunn', "J.D. Mesnard", "Catherine Miranda"]),
    ("Federalism and Family Law", "Mark Finchem", "Hildy Angius", ["Frank Carroll", "Eva Diaz", "Analise Ortiz", "Kevin Payne", "Priya Sundareshan"]),
    ("Finance", "J.D. Mesnard", 'Venden "Vince" Leach', ["Shawnna Bolick", "Flavio Bravo", 'Denise "Mitzi" Epstein', "Brian Fernandez", "Jake Hoffman"]),
    ("Government", "Jake Hoffman", "Wendy Rogers", ["Flavio Bravo", "Eva Diaz", "David C. Farnsworth", "John Kavanagh", "Lauren Kuby"]),
    ("Health and Human Services", "Carine Werner", 'Thomas "T.J." Shope', ["Hildy Angius", "Rosanna Gabaldón", "Sally Ann Gonzales", "Kiana Sears", "Janae Shamp"]),
    ("Judiciary and Elections", "Wendy Rogers", "John Kavanagh", ["Shawnna Bolick", "Mark Finchem", "Theresa Hatathlie", "Lauren Kuby", "Analise Ortiz"]),
    ("Military Affairs and Border Security", "David Gowan", "Janae Shamp", ['Timothy "Tim" Dunn', "Sally Ann Gonzales", "Catherine Miranda", "Wendy Rogers", "Kiana Sears"]),
    ("Natural Resources", 'Thomas "T.J." Shope', 'Timothy "Tim" Dunn', ["Frank Carroll", "Rosanna Gabaldón", "David Gowan", "Theresa Hatathlie", "Janae Shamp", "Priya Sundareshan"]),
    ("Public Safety", "Kevin Payne", "David C. Farnsworth", ["Lela Alston", "Rosanna Gabaldón", "David Gowan", "Kiana Sears", 'Thomas "T.J." Shope']),
    ("Regulatory Affairs and Government Efficiency", "Shawnna Bolick", "Frank Carroll", ['Denise "Mitzi" Epstein', "Brian Fernandez", 'Venden "Vince" Leach', "Analise Ortiz", "Kevin Payne"]),
    ("Rules", "David C. Farnsworth", "John Kavanagh", ["Lela Alston", "Frank Carroll", "Rosanna Gabaldón", "Catherine Miranda", "Warren Petersen", 'Thomas "T.J." Shope', "Priya Sundareshan"]),
]

HOUSE = [
    ("Appropriations", "Livingston", "Gress", ["Austin", "Blackman", "Blattman", "Diaz", "Gutierrez", "Lopez", "Nguyen", "Olson", "Rivero", "Sandoval", "Stahl Hamilton", "Travers", "Volk", "Way", "Weninger", "Willoughby"]),
    ("Artificial Intelligence & Innovation", "Wilmeth", "Taylor", ["Cavero", "Kupper", "Travers", "Villegas", "Willoughby"]),
    ("Commerce", "Weninger", "Way", ["Aguilar", "Blackman", "Carter N.", "Cavero", "Connolly", "Diaz", "Hendrix", "Villegas", "Wilmeth"]),
    ("Education", "Gress", "Peña", ["Abeytia", "Biasiucci", "Fink", "Garcia", "Gutierrez", "Hernandez L.", "Marshall", "Olson", "Rivero", "Simacek"]),
    ("Federalism, Military Affairs & Elections", "Gillette", "Keshel", ["Garcia", "Hernandez L.", "Kolodin", "Marquez", "Powell"]),
    ("Government", "Blackman", "Fink", ["Gillette", "Keshel", "Marquez", "Stahl Hamilton", "Villegas"]),
    ("Health & Human Services", "Bliss", "Heap", ["Contreras P.", "Gress", "Hernandez A.", "Kupper", "Liguori", "Lopez", "Luna-Nájera", "Mathis", "Pingerelli", "Weninger"]),
    ("International Trade", "Rivero", "Peña", ["Austin", "Carbone", "Cavero", "Hendrix", "Hernandez C.", "Travers", "Weninger", "Wilmeth"]),
    ("Judiciary", "Nguyen", "Powell", ["Bliss", "Contreras L.", "Diaz", "Garcia", "Hernandez A.", "Marshall", "Reim", "Way"]),
    ("Land, Agriculture & Rural Affairs", "Diaz", "Peña", ["Griffin", "Keshel", "Martinez", "Peshlakai", "Sandoval", "Stahl Hamilton"]),
    ("Natural Resources, Energy & Water", "Griffin", "Lopez", ["Carter P.", "Contreras P.", "Heap", "Liguori", "Martinez", "Mathis", "Peshlakai", "Taylor"]),
    ("Public Safety & Law Enforcement", "Marshall", "Carter P.", ["Abeytia", "Austin", "Crews", "Gillette", "Kolodin", "Nguyen", "Powell", "Reim", "Simacek", "Taylor", "Tsosie", "Volk"]),
    ("Regulatory Oversight", None, "Kolodin", ["Contreras L.", "Hernandez C.", "Keshel"]),
    ("Rules", "Hendrix", "Carter N.", ["Carbone", "Contreras L.", "De Los Santos", "Mathis", "Montenegro", "Willoughby"]),
    ("Rural Economic Development", "Martinez", "Lopez", ["Biasiucci", "Blackman", "Hernandez C.", "Peshlakai", "Volk"]),
    ("Science & Technology", "Pingerelli", "Wilmeth", ["Aguilar", "Cavero", "Connolly", "Fink", "Heap", "Hendrix", "Liguori"]),
    ("Transportation & Infrastructure", "Biasiucci", "Martinez", ["Bliss", "Carter P.", "Contreras P.", "Hernandez C.", "Tsosie"]),
    ("Ways & Means", "Olson", "Kupper", ["Blattman", "Carter N.", "Crews", "Livingston", "Luna-Nájera", "Taylor"]),
]

# Joint committees: (committee, chamber of member, chair, members)
JOINT = [
    ("Joint Legislative Budget Committee", "S", "David C. Farnsworth",
     ["Lela Alston", "Brian Fernandez", "Mark Finchem", "John Kavanagh", "Lauren Kuby", "J.D. Mesnard", "Carine Werner"]),
    ("Joint Legislative Budget Committee", "H", None,
     ["David Livingston", "Lorena Austin", "Seth Blattman", "Michael Carbone", "Matt Gress", "Justin Olson", "Stephanie Stahl Hamilton", "Michael Way"]),
    ("Joint Legislative Audit Committee", "S", None,
     ["Mark Finchem", "Flavio Bravo", 'Timothy "Tim" Dunn', "David C. Farnsworth", "Catherine Miranda", "Warren Petersen"]),
    ("Joint Legislative Audit Committee", "H", "Matt Gress",
     ["Michael Carbone", "Michele Peña", "Stephanie Stahl Hamilton", "Betty J Villegas", "Steve Montenegro"]),
]


def fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def build_index(members):
    by_full, by_house_key = {}, {}
    for m in members:
        by_full[fold(m["name"])] = m
        if m["chamber"] == "H":
            parts = re.sub(r",?\s+Sr\.?$", "", m["name"]).split()
            last = " ".join(parts[-2:]) if parts[-2:] == ["Stahl", "Hamilton"] or parts[-3:-1] == ["De", "Los"] else parts[-1]
            if parts[-3:-1] == ["De", "Los"]:
                last = " ".join(parts[-3:])
            by_house_key.setdefault(fold(last), []).append(m)
    return by_full, by_house_key


def find_house(key, idx):
    key = key.strip()
    m = re.match(r"^(.*?)\s+([A-Z])\.$", key)
    last, initial = (m.group(1), m.group(2)) if m else (key, None)
    cands = idx.get(fold(last), [])
    if initial:
        cands = [c for c in cands if c["name"].startswith(initial)]
    if len(cands) != 1:
        raise KeyError(f"House name '{key}' matched {len(cands)} members")
    return cands[0]


def main():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    members = payload["members"]
    for m in members:
        m["committees"] = []
    by_full, by_house = build_index(members)
    committees, skipped = [], []

    def assign(m, cname, chamber_key, role):
        if m["status"] != "active":
            skipped.append(f"{m['name']} ({cname})")
            return None
        m["committees"].append({
            "name": cname,
            "chamber": chamber_key,
            "role": role,
            "focus": PRIORITY.get(f"{chamber_key}:{cname}"),
        })
        return m["id"]

    for chamber_key, rows, finder in (("S", SENATE, lambda n: by_full[fold(n)]),
                                      ("H", HOUSE, lambda n: find_house(n, by_house))):
        for cname, chair, vice, others in rows:
            roster = []
            for name, role in [(chair, "Chair"), (vice, "Vice Chair")] + [(o, "Member") for o in others]:
                if not name:
                    continue
                mid = assign(finder(name), cname, chamber_key, role)
                if mid:
                    roster.append({"id": mid, "role": role})
            committees.append({
                "name": cname, "chamber": chamber_key, "focus": PRIORITY.get(f"{chamber_key}:{cname}"),
                "chair_vacant": chair is None, "members": roster, "source": SOURCES[chamber_key],
            })

    joint = {}
    for cname, ch, chair, names in JOINT:
        entry = joint.setdefault(cname, {"name": cname, "chamber": "J", "focus": PRIORITY.get(f"J:{cname}"),
                                          "chair_vacant": False, "members": [], "source": SOURCES["J"]})
        for n in names + ([chair] if chair and chair not in names else []):
            role = "Chair" if n == chair else "Member"
            mid = assign(by_full[fold(n)], cname, "J", role)
            if mid:
                entry["members"].append({"id": mid, "role": role})
    committees.extend(joint.values())

    payload["committee_sources"] = SOURCES
    DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / "committees.json").write_text(json.dumps({"committees": committees}, indent=2, ensure_ascii=False), encoding="utf-8")

    active = [m for m in members if m["status"] == "active"]
    none = [m["name"] for m in active if not m["committees"]]
    print(f"{len(committees)} committees, {sum(len(c['members']) for c in committees)} seats assigned")
    print("skipped (no longer in office):", ", ".join(skipped) or "none")
    print("active members with no listed assignment:", ", ".join(none) or "none")


if __name__ == "__main__":
    main()
