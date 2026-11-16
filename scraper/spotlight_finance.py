"""
Campaign finance summaries from the Arizona Secretary of State's free Spotlight
API (https://spotlightv2.arizona.vote/Reporting/Api). No key needed.

    pip install requests
    python scraper/spotlight_finance.py                 # summaries for current legislators
    python scraper/spotlight_finance.py --candidates    # also list 2026 legislative candidates

What it does
  1. Finds each legislator's candidate committees with the API's name search.
     Candidates usually register a new committee for each race, so a member
     can have several (e.g. a 2020 Senate committee and a 2024 one). Every
     committee whose candidate name matches and whose office is a legislative
     seat (or blank) is kept. Matches are saved to private/spotlight_committees.csv.
     If one is wrong, put the right committee id(s) in the override_id column
     (separate several with ";") and rerun.
  2. Pulls each committee's transactions per election cycle and sums them.
     The API's committee feed also lists other groups' spending about the
     committee; those rows are dropped. Only totals and categories are kept.
     No donor names are stored.
  3. With --candidates, lists everyone with a 2026 State Senate or State House
     candidate committee in data/candidates_2026.csv, marked new or current,
     to help fill data/members_elect.csv once results are certified.

Output (private, not committed): private/campaign_finance.json

Contributions show who funds a campaign. They don't show how a legislator votes,
so briefs should present them as context only.

Field names were checked against live responses on 2026-11-16
(transactionTypeDispositionName = Income/Expense, transactionGroupNumber =
contributor entity group, committeeId = the committee that filed the row).
Spot-check one legislator against the Spotlight site before relying on totals.
"""
import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
BASE = "https://spotlightv2.arizona.vote/api"
# Spotlight sits behind Cloudflare, which can block scripts that send an unusual
# User-Agent. A standard browser string avoids that; the request rate stays low.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36 (AZ SBDC legislative research)",
      "Accept": "application/json"}
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
            try:
                r = self.s.get(BASE + path, params=params, timeout=90)
            except requests.RequestException as e:
                sys.exit(f"Couldn't reach Spotlight ({BASE + path}): {e}")
            ctype = r.headers.get("content-type", "")
            if r.status_code in (403, 429, 503) or "json" not in ctype:
                sys.exit(f"Spotlight returned HTTP {r.status_code} ({ctype or 'no content type'}) for {r.url}\n"
                         f"This usually means its firewall blocked the script. First 200 characters:\n{r.text[:200]}")
            r.raise_for_status()
            self.cache[key] = r.json()
            time.sleep(self.delay)
        return self.cache[key]

    def paged(self, path, **params):
        page = 1
        while True:
            doc = self.get(path, page=page, pageSize=500, **params)
            rows = pick(doc, "data", default=doc if isinstance(doc, list) else []) or []
            yield from rows
            total = int(pick(doc, "totalCount", default=len(rows)) or 0)
            if not rows or page * 500 >= total:
                break
            page += 1


def plain(text):
    """Lowercase without accents: Spotlight labels drop them (Gabaldón -> gabaldon)."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def name_parts(name):
    n = re.sub(r'["\u201c\u201d][^"\u201c\u201d]*["\u201c\u201d]', " ", name)
    n = re.sub(r",?\s+(Sr|Jr)\.?$", "", n)
    parts = [p for p in re.split(r"\s+", n.strip()) if len(p.rstrip(".")) > 1]
    return parts[0].lower(), parts[-1].lower()


def name_keys(name):
    """(first-name prefixes, last name) for matching search labels.
    Includes a quoted nickname, so Denise "Mitzi" Epstein also matches "Mitzi"."""
    first, last = name_parts(name)
    firsts = {plain(first).replace(".", "")[:3]}
    for nick in re.findall(r'["\u201c]([^"\u201d]+)["\u201d]', name):
        firsts.add(plain(nick).replace(".", "").strip()[:3])
    return {f for f in firsts if f}, plain(last)


LEGISLATIVE_OFFICE = re.compile(r"state senat|state rep|legislat", re.I)


def find_committees(api, member):
    """All candidate committees that look like this member's legislative campaigns.

    Returns (list of committee ids, note). Search results are labelled
    "Candidate Name - Committee Name Address", e.g. "Frank Carroll - Vote Frank
    Carroll Po Box ...". The first name is checked loosely (first three letters)
    so Tim/Timothy and Bob/Robert-style variants mostly still match."""
    firsts, last = name_keys(member["name"])
    res = api.get("/entities/search", name=last)
    rows = pick(res, "data", default=res if isinstance(res, list) else []) or []
    ids = []
    for r in rows:
        if int(pick(r, "entityGroupNumber", default=0) or 0) != 1:
            continue
        # Labels look like "Frank Carroll - Vote Frank Carroll Po Box ..."; match the
        # candidate part only, so an address ("Ste 2-142") can't satisfy "Steve".
        who = plain(str(pick(r, "name", default="")).split(" - ")[0]).replace(".", "")
        if last not in who or not any(re.search(r"\b" + re.escape(f), who) for f in firsts):
            continue
        cid = pick(r, "entityId", "id")
        detail = pick(api.get(f"/committees/{cid}"), "committee", default={}) or {}
        office = str(pick(detail, "officeName", default="") or "")
        if office and not LEGISLATIVE_OFFICE.search(office):
            continue  # same name, different race (city council, corporation commission, ...)
        ids.append(cid)
    if not ids:
        return [], "no match; set override_id"
    return ids, f"{len(ids)} committee(s) by name search; verify in spotlight_committees.csv"


def own_transactions(api, committee_id, cycle_id):
    """Rows the committee itself filed, without others' spending about it."""
    for t in api.paged(f"/committees/{committee_id}/transactions", cycleId=cycle_id):
        if str(pick(t, "committeeId", default=committee_id)) == str(committee_id):
            yield t


def summarize(transactions):
    out = {"receipts": 0.0, "contributions": 0, "expenses": 0.0, "by_source": {}, "in_state": 0.0,
           "out_of_state": 0.0, "business_community": 0.0}
    for t in transactions:
        amt = float(pick(t, "amount", default=0) or 0)
        kind = str(pick(t, "transactionTypeDispositionName", default="")).lower()
        if kind.startswith("expense"):
            out["expenses"] += abs(amt)
            continue
        if not kind.startswith("income") or amt <= 0:
            continue  # loans, refunds and reversals aren't counted as money raised
        out["receipts"] += amt
        out["contributions"] += 1
        g = pick(t, "transactionGroupNumber")
        src = GROUPS.get(int(g), "Other") if str(g or "").isdigit() else "Other"
        out["by_source"][src] = out["by_source"].get(src, 0.0) + amt
        st = str(pick(t, "state", default="")).upper()
        if st == "AZ":
            out["in_state"] += amt
        elif len(st) == 2:
            out["out_of_state"] += amt
        occ = " ".join(str(pick(t, f, default="")) for f in ("occupation", "employer"))
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
    """Regular election cycles only; recall and special cycles share years with them."""
    doc = api.get("/cycles")
    rows = pick(doc, "data", default=doc if isinstance(doc, list) else []) or []
    found = {}
    for r in rows:
        name = str(pick(r, "cycleName", "name", default="")).strip()
        cid = pick(r, "cycleId", "id")
        if pick(r, "isSpecialCycle", default=False) or pick(r, "isRecallCycle", default=False):
            continue
        for y in years:
            if name == str(y) and cid is not None:
                found[y] = cid
    return found


def load_overrides(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {int(r["member_id"]): [x.strip() for x in r["override_id"].split(";") if x.strip()]
                for r in csv.DictReader(f) if r.get("override_id", "").strip()}


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
        ids, note = (overrides[m["id"]], "manual override") if m["id"] in overrides else find_committees(api, m)
        matches.append({"member_id": m["id"], "name": m["name"], "chamber": m["chamber"], "district": m["district"],
                        "committee_ids": ";".join(str(x) for x in ids), "match_note": note,
                        "override_id": ";".join(overrides.get(m["id"], []))})
        if not ids:
            print(f"  [{i}/{len(members)}] {m['name']}: no committee found")
            continue
        per_cycle = {}
        for y, c in cyc.items():
            tx, used = [], []
            for cid in ids:
                rows = list(own_transactions(api, cid, c))
                if rows:
                    tx += rows
                    used.append(str(cid))
            if tx:
                per_cycle[str(y)] = {**summarize(tx), "committees": used}
        results[m["id"]] = {"name": m["name"], "committee_id": "; ".join(str(x) for x in ids),
                            "match_note": note, "cycles": per_cycle}
        print(f"  [{i}/{len(members)}] {m['name']}: {len(ids)} committee(s), data in {len(per_cycle)} cycle(s)"
              + "".join(f"; {y}: ${v['receipts']:,.0f} raised" for y, v in sorted(per_cycle.items())))

    if not matches:
        sys.exit("No active legislators in data/legislators.json.")
    with (PRIVATE / "spotlight_committees.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
        w.writeheader()
        w.writerows(matches)

    (PRIVATE / "campaign_finance.json").write_text(json.dumps({
        "source": "Arizona Secretary of State Spotlight API", "retrieved": date.today().isoformat(),
        "method": {
            "business_community": "Contributions from entities the API classes as businesses or organizations, plus individuals whose occupation or employer names an owner, founder, executive or self-employed role.",
            "in_state": "Based on the contributor's state as reported. District-level location isn't available from the API.",
            "scope": "Income rows filed by the legislator's own candidate committees in each cycle, summed across committees. Expenses and others' independent expenditures are excluded from receipts.",
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
