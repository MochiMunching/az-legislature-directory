"""
Build data/members_elect.json from data/members_elect.csv.

Fill the CSV from the Secretary of State's certified results for the November 3
general election (one row per winner, both chambers):

    name,chamber,district,party,source_url,notes
    Jane Example,H,12,D,https://azsos.gov/...,

chamber is S or H. To get a head start, run
`python scraper/spotlight_finance.py --candidates`, which lists every 2026
legislative candidate committee in data/candidates_2026.csv; copy the winners
across once results are certified. Then run:

    python scraper/members_elect.py

Before certification you can load unofficial results, labelled as such on the site:

    python scraper/members_elect.py --status "Unofficial results as of Nov 13, 2026 ..."

Run it again without --status once the CSV holds certified results.

Each winner is compared with the current roster:
  returning      same person, same chamber
  switching      same person, moving between House and Senate
  new            not on the current roster  -> marked "needs briefing"
It also lists current members who don't appear among the winners, so you can
see every seat that will change hands in January.
"""
import argparse
import csv
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "members_elect.csv"
OUT = ROOT / "data" / "members_elect.json"
ROSTER = ROOT / "data" / "legislators.json"


def key(name):
    """Loose name key: accents, quotes, nicknames, initials and suffixes removed."""
    n = unicodedata.normalize("NFD", name)
    n = "".join(c for c in n if unicodedata.category(c) != "Mn").lower()
    n = re.sub(r'"[^"]*"', " ", n)
    n = re.sub(r"\b(jr|sr|ii|iii)\b\.?", " ", n)
    n = re.sub(r"\b[a-z]\.?(?=\s)", " ", n)          # middle initials
    parts = re.sub(r"[^a-z\s-]", " ", n).split()
    return (parts[0], parts[-1]) if parts else ("", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", help="label shown on the site, e.g. that results are unofficial and as of when")
    args = ap.parse_args()
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    current = [m for m in roster["members"] if m["status"] == "active"]
    by_key = {key(m["name"]): m for m in current}

    rows = []
    if CSV.exists():
        with CSV.open(encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if (r.get("name") or "").strip()]

    elect, matched_ids = [], set()
    for r in rows:
        ch = r["chamber"].strip().upper()[:1]
        m = by_key.get(key(r["name"]))
        if m:
            matched_ids.add(m["id"])
            status = "returning" if m["chamber"] == ch else "switching"
        else:
            status = "new"
        elect.append({
            "name": r["name"].strip(), "chamber": ch, "district": int(r["district"]),
            "party": r.get("party", "").strip().upper()[:1] or None,
            "status": status,
            "current_member_id": m["id"] if m else None,
            "briefing": "needs briefing" if status != "returning" else "existing relationship",
            "source_url": r.get("source_url") or None, "notes": r.get("notes") or None,
        })

    departing = [] if not rows else [
        {"member_id": m["id"], "name": m["name"], "chamber": m["chamber"], "district": m["district"], "party": m["party"]}
        for m in current if m["id"] not in matched_ids
    ]

    OUT.write_text(json.dumps({
        "election": "2026-11-03 general election",
        "updated": date.today().isoformat(),
        "source": "data/members_elect.csv (from Secretary of State results)",
        "results_status": args.status or "Certified results",
        "members_elect": sorted(elect, key=lambda e: (e["district"], e["chamber"] != "S", e["name"])),
        "departing": departing,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {s: sum(e["status"] == s for e in elect) for s in ("returning", "switching", "new")}
    print(f"{len(elect)} winners: {counts}; {len(departing)} current members not returning")
    if rows and len(elect) != 90:
        print(f"Note: expected 90 winners, CSV has {len(elect)}")


if __name__ == "__main__":
    main()
