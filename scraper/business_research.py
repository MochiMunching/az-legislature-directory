"""
Business background research for each legislator, kept in private/.

Source of record: the financial disclosure statement each legislator files
with the Secretary of State (A.R.S. 38-542). Statements list business
interests over $1,000, businesses where they held an office or fiduciary role,
income sources and business licenses. Find them from the Secretary of State's
financial disclosure index on azsos.gov. Then verify each business in ACC eCorp
(free entity search on azcc.gov): entity number, status, formation date.

    python scraper/business_research.py init     # create private/business_background.csv
    python scraper/business_research.py check    # validate and build private/business_background.json

The CSV starts with one row per legislator. Add one row per business interest
(repeat the member_id). If a statement lists no business interests, leave
business_name blank and set interest_type to none_reported.

interest_type is one of:
  ownership          interest in a business (A.R.S. 38-542, over $1,000)
  office_role        officer, director, or fiduciary role in a business
  income_source      business that paid them over $1,000
  business_license   license held by them or a business they have an interest in
  none_reported      the statement lists no business interests
The reported-business-ties flag is set only from what the legislator reported,
never from name matches in business records.
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
CSV_PATH = PRIVATE / "business_background.csv"
FIELDS = ["member_id", "legislator", "chamber", "district",
          "interest_type", "business_name", "role_or_description", "disclosure_year", "disclosure_url",
          "acc_entity_number", "acc_status", "acc_formed", "acc_url",
          "researched_by", "researched_on", "notes"]
TYPES = {"ownership", "office_role", "income_source", "business_license", "none_reported"}
TIE_TYPES = {"ownership", "office_role", "business_license"}


def roster():
    data = json.loads((ROOT / "data" / "legislators.json").read_text(encoding="utf-8"))
    return {m["id"]: m for m in data["members"] if m["status"] == "active"}


def init():
    PRIVATE.mkdir(exist_ok=True)
    if CSV_PATH.exists():
        sys.exit(f"{CSV_PATH.relative_to(ROOT)} already exists; not overwriting.")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for m in sorted(roster().values(), key=lambda m: (m["district"], m["chamber"] != "S", m["name"])):
            w.writerow({"member_id": m["id"], "legislator": m["name"], "chamber": m["chamber"], "district": m["district"]})
    print(f"Created {CSV_PATH.relative_to(ROOT)} with one row per legislator.")


def check():
    members = roster()
    if not CSV_PATH.exists():
        sys.exit("Run `python scraper/business_research.py init` first.")
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    problems, by_member = [], {}
    for n, r in enumerate(rows, 2):
        try:
            mid = int(r["member_id"])
        except (TypeError, ValueError):
            problems.append(f"line {n}: member_id missing or not a number")
            continue
        if mid not in members:
            problems.append(f"line {n}: member_id {mid} isn't an active legislator")
            continue
        t = (r.get("interest_type") or "").strip()
        if not t and not (r.get("business_name") or "").strip():
            by_member.setdefault(mid, [])
            continue
        if t not in TYPES:
            problems.append(f"line {n} ({members[mid]['name']}): interest_type '{t}' should be one of {sorted(TYPES)}")
            continue
        if not (r.get("disclosure_url") or "").strip():
            problems.append(f"line {n} ({members[mid]['name']}): add disclosure_url so every entry has a source")
        if t != "none_reported" and not (r.get("business_name") or "").strip():
            problems.append(f"line {n} ({members[mid]['name']}): business_name is empty")
        by_member.setdefault(mid, []).append({k: (r.get(k) or "").strip() for k in FIELDS[4:]})

    out = {}
    for mid, m in members.items():
        entries = [e for e in by_member.get(mid, [])]
        reviewed = bool(entries)
        ties = [e for e in entries if e["interest_type"] in TIE_TYPES]
        out[mid] = {
            "name": m["name"],
            "status": "not reviewed" if not reviewed else ("reported business ties" if ties else "no business ties reported"),
            "reported_business_ties": len(ties),
            "verified_in_acc": sum(1 for e in ties if e["acc_entity_number"]),
            "entries": [e for e in entries if e["interest_type"] != "none_reported"],
            "sources": sorted({e["disclosure_url"] for e in entries if e["disclosure_url"]}),
        }

    (PRIVATE / "business_background.json").write_text(json.dumps({
        "updated": date.today().isoformat(),
        "method": "From legislators' own financial disclosure statements (A.R.S. 38-542), with businesses verified in ACC eCorp where possible.",
        "members": out}, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {}
    for v in out.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print("Wrote private/business_background.json:", counts)
    if problems:
        print(f"{len(problems)} row(s) to fix:")
        for p in problems:
            print("  " + p)


if __name__ == "__main__":
    {"init": init, "check": check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
