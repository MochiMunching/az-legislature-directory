"""
Campaign finance summaries from the Arizona Secretary of State's free Spotlight
API (https://spotlightv2.arizona.vote/Reporting/Api). No key needed.

    pip install requests
    python scraper/spotlight_finance.py                 # summaries for current legislators
    python scraper/spotlight_finance.py --candidates    # also list 2026 legislative candidates

What it does
  1. Finds each legislator's candidate committee with the API's name search.
     Matches are saved to private/spotlight_committees.csv. If one is wrong,
     put the right committee id in the override_id column and rerun.
  2. Pulls that committee's transactions per election cycle and summarizes them.
     Only totals and categories are kept. No donor names are stored.
  3. With --candidates, lists everyone with a 2026 State Senate or State House
     candidate committee in data/candidates_2026.csv, marked new or current,
     to help fill data/members_elect.csv once results are certified.

Output (private, not committed): private/campaign_finance.json

Contributions show who funds a campaign. They don't show how a legislator votes,
so briefs should present them as context only.

The API documents its endpoints but not every response field, so field names
are read defensively. Check the first run's output against a committee page on
the Spotlight site before relying on it.
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
BASE = "https://spotlightv2.arizona.vote/api"
UA = {"User-Agent": "AZ-SBDC-legislative-directory/0.1 (research prototype)"}
GROUPS = {1: "Candidate", 2: "PAC", 3: "Party", 4: "Organization", 5: "Independent expenditure",
          6: "Proposition", 7: "Individual", 8: "Business"}
BUSINESS_ROLE = re.compile(r"\b(owner|self[- ]employed|proprietor|founder|co-?founder|president|ceo|principal|"
                           r"partner|entrepreneur|small business|business owner|managing member)\b", re.I)


def pick(obj, *names, default=None):
    """Read the first present key, case-insensitively."""
    if not isinstance(obj, dict):
        return default
    low = {k.lower(): v for k, v in obj.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return default


class Spotlight:
    def __init__(self, delay=0.4):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.delay = delay
        self.cache = {}

    def get(self, path, **params):
        key = (path, tuple(sorted(params.items())))
        if key not in self.cache:
            r = self.s.get(BASE + path, params=params, timeout=60)
            r.raise_for_status()
            self.cache[key] = r.json()
            time.sleep(self.delay)
        return self.cache[key]

    def paged(self, path, **params):
        page = 1
        while True:
            doc = self.get(path, page=page, pageSize=500, **params)
            rows = pick(doc, "data", default=doc if isinstance(doc, list) else [])
            yield from rows
            total = pick(doc, "totalCount", default=len(rows))
            if not rows or page * 500 >= total:
                break
            page += 1


def name_parts(name):
    n = re.sub(r'"[^"]*"', " ", name)
    n = re.sub(r",?\s+(Sr|Jr)\.?$", "", n)
    parts = [p for p in re.split(r"\s+", n.strip()) if len(p.rstrip(".")) > 1]
    return parts[0].lower(), parts[-1].lower()


def find_committee(api, member):
    first, last = name_parts(member["name"])
    res = api.get("/entities/search", name=last)
    rows = pick(res, "data", default=res if isinstance(res, list) else [])
    cands, last_only = [], []
    for r in rows:
        if int(pick(r, "entityGroupNumber", "entityGroup", default=0) or 0) != 1:
            continue
        label = str(pick(r, "name", "entityName", "committeeName", "candidateName", default="")).lower()
        if last not in label:
            continue
        if first[:3] in label:
            office = str(pick(r, "office", "officeName", default="")).lower()
            score = 2 if (("senat" in office) == (member["chamber"] == "S") and office) else 1
            cands.append((score, r))
        else:
            last_only.append(r)
    if not cands:
        if len(last_only) == 1:
            return pick(last_only[0], "entityId", "id"), "last name only; verify in spotlight_committees.csv"
        return None, "no match" if not last_only else f"{len(last_only)} last-name-only matches; set override_id"
    cands.sort(key=lambda x: -x[0])
    best = cands[0][1]
    note = "single match" if len(cands) == 1 else f"{len(cands)} candidate committees found; picked the best office match"
    return pick(best, "entityId", "id"), note


def summarize(transactions, member_district=None):
    out = {"receipts": 0.0, "contributions": 0, "expenses": 0.0, "by_source": {}, "in_state": 0.0,
           "out_of_state": 0.0, "business_community": 0.0}
    for t in transactions:
        amt = float(pick(t, "amount", "transactionAmount", default=0) or 0)
        kind = str(pick(t, "transactionType", "type", "category", default="")).lower()
        is_expense = bool(pick(t, "isExpense", default=False)) or "expen" in kind
        if is_expense:
            out["expenses"] += abs(amt)
            continue
        if amt <= 0:
            continue
        out["receipts"] += amt
        out["contributions"] += 1
        g = pick(t, "contributorEntityGroupNumber", "entityGroupNumber", "contributorGroup")
        src = GROUPS.get(int(g), "Other") if str(g or "").isdigit() else (
            "Individual" if pick(t, "occupation", "contributorOccupation") else "Other")
        out["by_source"][src] = out["by_source"].get(src, 0.0) + amt
        st = str(pick(t, "state", "contributorState", default="")).upper()
        if st == "AZ":
            out["in_state"] += amt
        elif st:
            out["out_of_state"] += amt
        occ = " ".join(str(pick(t, f, default="")) for f in ("occupation", "contributorOccupation", "employer", "contributorEmployer"))
        if src in ("Business", "Organization") or (src == "Individual" and BUSINESS_ROLE.search(occ)):
            out["business_community"] += amt
    r = out["receipts"] or 1
    out["shares"] = {
        "in_state": round(out["in_state"] / r, 3),
        "out_of_state": round(out["out_of_state"] / r, 3),
        "business_community": round(out["business_community"] / r, 3),
        **{f"source_{k.lower().replace(' ', '_')}": round(v / r, 3) for k, v in out["by_source"].items()},
    }
    for k in ("receipts", "expenses", "in_state", "out_of_state", "business_community"):
        out[k] = round(out[k], 2)
    out["by_source"] = {k: round(v, 2) for k, v in sorted(out["by_source"].items(), key=lambda x: -x[1])}
    return out


def cycles(api, years):
    doc = api.get("/cycles")
    rows = pick(doc, "data", default=doc if isinstance(doc, list) else [])
    found = {}
    for r in rows:
        label = str(pick(r, "name", "cycleName", "year", default=""))
        cid = pick(r, "cycleId", "id")
        for y in years:
            if str(y) in label and cid is not None:
                found[y] = cid
    return found


def load_overrides(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {int(r["member_id"]): r["override_id"].strip() for r in csv.DictReader(f) if r.get("override_id", "").strip()}


def list_candidates(api, cycle_id, roster):
    """Everyone with a 2026 legislative candidate committee, from office-filtered transactions."""
    doc = api.get("/offices")
    offices = pick(doc, "data", default=doc if isinstance(doc, list) else [])
    leg = []
    for o in offices:
        name = str(pick(o, "name", "officeName", default=""))
        if re.search(r"state senat|state rep", name, re.I):
            m = re.search(r"(\d+)", name)
            leg.append((pick(o, "officeID", "officeId", "id"), "S" if "senat" in name.lower() else "H", int(m.group(1)) if m else None))
    seen = {}
    for oid, ch, dist in leg:
        for t in api.paged("/transactions/search", officeId=oid, cycleId=cycle_id, filerTypeId=1,
                           startDate="2025-01-01", endDate=date.today().isoformat()):
            fid = pick(t, "filerId", "committeeId")
            nm = pick(t, "filerName", "committeeName", "candidateName")
            if fid and fid not in seen:
                seen[fid] = {"filer_id": fid, "name": nm, "chamber": ch, "district": dist}
    keys = {name_parts(m["name"]) for m in roster if m["status"] == "active"}
    rows = []
    for c in seen.values():
        try:
            current = name_parts(re.sub(r"(?i)\b(for|committee|to elect|campaign)\b.*", "", c["name"] or "")) in keys
        except IndexError:
            current = False
        rows.append({**c, "on_current_roster": "yes" if current else "no"})
    return sorted(rows, key=lambda r: (r["district"] or 99, r["chamber"], str(r["name"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2022,2024,2026", help="election cycles to summarize")
    ap.add_argument("--candidates", action="store_true", help="also list 2026 legislative candidates")
    ap.add_argument("--limit", type=int, help="only the first N legislators (for a quick test)")
    args = ap.parse_args()

    api = Spotlight()
    roster = json.loads((ROOT / "data" / "legislators.json").read_text(encoding="utf-8"))["members"]
    members = [m for m in roster if m["status"] == "active"][: args.limit]
    years = [int(y) for y in args.years.split(",")]
    cyc = cycles(api, years)
    if not cyc:
        sys.exit("Couldn't read election cycles from /api/cycles. Check the API is reachable.")
    print("cycles:", cyc)

    PRIVATE.mkdir(exist_ok=True)
    overrides = load_overrides(PRIVATE / "spotlight_committees.csv")
    matches, results = [], {}
    for i, m in enumerate(members, 1):
        cid, note = (overrides[m["id"]], "manual override") if m["id"] in overrides else find_committee(api, m)
        matches.append({"member_id": m["id"], "name": m["name"], "chamber": m["chamber"], "district": m["district"],
                        "committee_id": cid or "", "match_note": note, "override_id": overrides.get(m["id"], "")})
        if not cid:
            print(f"  [{i}/{len(members)}] {m['name']}: no committee found")
            continue
        per_cycle = {}
        for y, c in cyc.items():
            tx = list(api.paged(f"/committees/{cid}/transactions", cycleId=c))
            if tx:
                per_cycle[str(y)] = summarize(tx)
        results[m["id"]] = {"name": m["name"], "committee_id": cid, "match_note": note, "cycles": per_cycle}
        print(f"  [{i}/{len(members)}] {m['name']}: committee {cid}, {len(per_cycle)} cycle(s)")

    with (PRIVATE / "spotlight_committees.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
        w.writeheader()
        w.writerows(matches)

    (PRIVATE / "campaign_finance.json").write_text(json.dumps({
        "source": "Arizona Secretary of State Spotlight API", "retrieved": date.today().isoformat(),
        "method": {
            "business_community": "Contributions from entities the API classes as businesses or organizations, plus individuals whose occupation or employer names an owner, founder, executive or self-employed role.",
            "in_state": "Based on the contributor's state as reported. District-level location isn't available from the API.",
        },
        "legislators": results,
    }, indent=2), encoding="utf-8")
    print(f"Wrote private/campaign_finance.json for {len(results)} legislators")

    if args.candidates and 2026 in cyc:
        rows = list_candidates(api, cyc[2026], roster)
        out = ROOT / "data" / "candidates_2026.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["filer_id", "name", "chamber", "district", "on_current_roster"])
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {out.name}: {len(rows)} candidate committees, {sum(r['on_current_roster'] == 'no' for r in rows)} not on the current roster")


if __name__ == "__main__":
    main()
