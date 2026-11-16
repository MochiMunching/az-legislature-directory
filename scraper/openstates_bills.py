"""
Bills, sponsorships and roll-call votes from the Open States API v3 (free key
from https://open.pluralpolicy.com, profile page).

    pip install requests
    export OPENSTATES_API_KEY=your-key            (Windows: set OPENSTATES_API_KEY=your-key)
    python scraper/openstates_bills.py --discover   # find candidate bills by topic keyword
    python scraper/openstates_bills.py              # refresh tracked bills, votes, ESOP watch

How the bill list works
  --discover searches the session for small business, tax, regulatory, workforce
  and ESOP keywords and adds new matches to data/bill_list.csv with track blank.
  SBDC staff review that file and set track=yes on the bills that matter.
  Only track=yes bills get votes pulled. The keyword list finds candidates;
  SBDC decides what counts.

Outputs (all public record, no scoring):
  data/bills.json       tracked bills: status, actions, sponsors, roll calls
  data/votes.json       each legislator's recorded votes on tracked bills
  data/esop_watch.json  any bill matching the employee-ownership keywords
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://v3.openstates.org"
JURISDICTION = "ocd-jurisdiction/country:us/state:az/government"
BILL_LIST = ROOT / "data" / "bill_list.csv"
LIST_FIELDS = ["session", "identifier", "title", "topic", "track", "openstates_id", "found_by", "notes"]

TOPICS = {
    "small business": ["small business", "microbusiness", "entrepreneur"],
    "tax": ["transaction privilege tax", "income tax credit", "business tax", "tax credit"],
    "regulatory": ["occupational licens", "regulatory relief", "business licens", "permitting"],
    "workforce": ["workforce development", "apprenticeship", "job training"],
    "economic development": ["commerce authority", "economic development", "rural development"],
    "ESOP": ["employee ownership", "employee stock ownership", "employee-owned", "worker cooperative",
             "business succession", "esop"],
}
ESOP_TERMS = TOPICS["ESOP"]


class OpenStates:
    def __init__(self, key, delay=1.1):
        self.s = requests.Session()
        self.s.headers.update({"X-API-KEY": key, "User-Agent": "AZ-SBDC-legislative-directory/0.1"})
        self.delay = delay

    def get(self, path, params=None):
        for attempt in range(4):
            r = self.s.get(BASE + path, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(self.delay)
            return r.json()
        r.raise_for_status()

    def paged(self, path, params):
        page = 1
        while True:
            doc = self.get(path, {**params, "page": page, "per_page": 20})
            yield from doc.get("results", [])
            pg = doc.get("pagination") or {}
            if page >= int(pg.get("max_page") or 1):
                break
            page += 1


def fold(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def name_key(name):
    n = re.sub(r'"[^"]*"', " ", fold(name))
    n = re.sub(r"\b(jr|sr|ii|iii)\b\.?", " ", n)
    parts = [p for p in re.sub(r"[^a-z\s-]", " ", n).split() if len(p) > 1]
    return (parts[0], parts[-1]) if parts else ("", "")


def current_session(api, wanted=None):
    doc = api.get(f"/jurisdictions/{JURISDICTION}", {"include": "legislative_sessions"})
    sessions = doc.get("legislative_sessions") or []
    if wanted:
        return wanted
    regular = [s for s in sessions if "special" not in (s.get("classification") or "") and "special" not in s.get("identifier", "")]
    regular.sort(key=lambda s: s.get("start_date") or s.get("identifier"))
    if not regular:
        sys.exit("Couldn't find Arizona sessions; pass --session, for example 57th-2nd-regular")
    return regular[-1]["identifier"]


def person_index(roster):
    """Roster lookup by (first, last) and by last name + chamber + district."""
    by_name, by_seat = {}, {}
    for m in roster:
        if m["status"] != "active":
            continue
        k = name_key(m["name"])
        by_name.setdefault(k, []).append(m)
        by_seat[(k[1], m["chamber"], m["district"])] = m
    return by_name, by_seat


def match_person(p, by_name, by_seat, chamber=None):
    """p is an Open States person or sponsor/voter object; returns roster member or None."""
    if not p:
        return None
    nm = p.get("name") or p.get("voter_name") or ""
    role = p.get("current_role") or {}
    ch = {"upper": "S", "lower": "H"}.get(role.get("org_classification"), chamber)
    dist = str(role.get("district") or "")
    k = name_key(nm)
    if dist.isdigit() and ch and (k[1], ch, int(dist)) in by_seat:
        return by_seat[(k[1], ch, int(dist))]
    hits = [m for m in by_name.get(k, []) if not ch or m["chamber"] == ch]
    if len(hits) == 1:
        return hits[0]
    # Roll calls often list "Last" or "Last, F." (initial added when two members share a last name)
    if not nm:
        return None
    head, _, tail = fold(nm).partition(",")
    last = head.split()[-1] if head.split() else ""
    initial = re.sub(r"[^a-z]", "", tail)[:1]
    hits = [m for ms in by_name.values() for m in ms if name_key(m["name"])[1] == last and (not ch or m["chamber"] == ch)]
    if initial and len(hits) > 1:
        hits = [m for m in hits if name_key(m["name"])[0].startswith(initial)]
    return hits[0] if len(hits) == 1 else None


def read_list():
    if not BILL_LIST.exists():
        return []
    with BILL_LIST.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_list(rows):
    with BILL_LIST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LIST_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LIST_FIELDS})


def discover(api, session):
    rows = read_list()
    have = {(r["session"], r["identifier"]) for r in rows}
    added = 0
    for topic, terms in TOPICS.items():
        for term in terms:
            for b in api.paged("/bills", {"jurisdiction": JURISDICTION, "session": session, "q": f'"{term}"'}):
                key = (session, b.get("identifier"))
                if key in have:
                    continue
                have.add(key)
                rows.append({"session": session, "identifier": b.get("identifier"), "title": b.get("title"),
                             "topic": topic, "track": "", "openstates_id": b.get("id"), "found_by": term})
                added += 1
    rows.sort(key=lambda r: (r["session"], r["identifier"]))
    write_list(rows)
    print(f"{added} new candidate bills added to {BILL_LIST.relative_to(ROOT)}. Set track=yes on the ones SBDC wants followed.")


def summarize_bill(b, by_name, by_seat):
    sponsors = []
    for s in b.get("sponsorships") or []:
        m = match_person(s.get("person") or {"name": s.get("name")}, by_name, by_seat)
        sponsors.append({"name": s.get("name"), "primary": bool(s.get("primary")),
                         "classification": s.get("classification"), "member_id": m["id"] if m else None})
    rolls = []
    for v in b.get("votes") or []:
        org = (v.get("organization") or {}).get("classification")
        ch = {"upper": "S", "lower": "H"}.get(org)
        counts = {c.get("option"): c.get("value") for c in v.get("counts") or []}
        votes = []
        for pv in v.get("votes") or []:
            m = match_person(pv.get("voter") or {"name": pv.get("voter_name")}, by_name, by_seat, ch)
            votes.append({"name": pv.get("voter_name") or (pv.get("voter") or {}).get("name"),
                          "option": pv.get("option"), "member_id": m["id"] if m else None})
        rolls.append({"id": v.get("id"), "date": (v.get("start_date") or "")[:10], "chamber": ch,
                      "motion": v.get("motion_text"), "result": v.get("result"), "counts": counts, "votes": votes})
    acts = b.get("actions") or []
    return {
        "id": b.get("id"), "identifier": b.get("identifier"), "title": b.get("title"),
        "session": (b.get("session") if isinstance(b.get("session"), str) else (b.get("session") or {}).get("identifier")),
        "chamber": {"upper": "S", "lower": "H"}.get((b.get("from_organization") or {}).get("classification")),
        "subjects": b.get("subject") or [],
        "latest_action": {"date": (b.get("latest_action_date") or "")[:10], "description": b.get("latest_action_description")},
        "actions": [{"date": (a.get("date") or "")[:10], "description": a.get("description"),
                     "classification": a.get("classification") or []} for a in acts][-12:],
        "sponsors": sponsors, "roll_calls": sorted(rolls, key=lambda r: r["date"]),
        "url": b.get("openstates_url"),
    }


def fetch_bill(api, row):
    params = [("include", i) for i in ("sponsorships", "votes", "actions")]
    if row.get("openstates_id"):
        return api.get(f"/bills/{row['openstates_id']}", params)
    ident = row["identifier"].replace(" ", "")
    return api.get(f"/bills/az/{row['session']}/{ident}", params)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="search for candidate bills by topic keyword")
    ap.add_argument("--session", help="Open States session id, e.g. 57th-2nd-regular (default: latest regular)")
    args = ap.parse_args()

    key = os.environ.get("OPENSTATES_API_KEY")
    if not key:
        sys.exit("Set OPENSTATES_API_KEY (free key from your profile at open.pluralpolicy.com).")
    api = OpenStates(key)
    session = current_session(api, args.session)
    print("session:", session)

    if args.discover:
        discover(api, session)
        return

    roster = json.loads((ROOT / "data" / "legislators.json").read_text(encoding="utf-8"))["members"]
    by_name, by_seat = person_index(roster)

    tracked = [r for r in read_list() if (r.get("track") or "").strip().lower() in ("yes", "y", "true", "1")]
    bills = []
    for r in tracked:
        try:
            b = summarize_bill(fetch_bill(api, r), by_name, by_seat)
        except requests.HTTPError as e:
            print(f"  ! {r['identifier']}: {e}")
            continue
        b["topic"], b["notes"] = r.get("topic"), r.get("notes")
        bills.append(b)
        print(f"  {b['identifier']}: {len(b['sponsors'])} sponsors, {len(b['roll_calls'])} roll calls")

    votes = {}
    for b in bills:
        for rc in b["roll_calls"]:
            for v in rc["votes"]:
                if v["member_id"]:
                    votes.setdefault(str(v["member_id"]), []).append({
                        "bill": b["identifier"], "title": b["title"], "topic": b.get("topic"), "date": rc["date"],
                        "motion": rc["motion"], "result": rc["result"], "option": v["option"]})
    unmatched = sorted({v["name"] for b in bills for rc in b["roll_calls"] for v in rc["votes"] if not v["member_id"]})

    esop = []
    for term in ESOP_TERMS:
        for b in api.paged("/bills", {"jurisdiction": JURISDICTION, "session": session, "q": f'"{term}"',
                                      "include": "sponsorships"}):
            if any(e["id"] == b.get("id") for e in esop):
                continue
            s = summarize_bill(b, by_name, by_seat)
            s["matched_term"] = term
            esop.append(s)

    today = date.today().isoformat()
    meta = {"source": "Open States API v3", "retrieved": today, "session": session}
    (ROOT / "data" / "bills.json").write_text(json.dumps({**meta, "bills": bills}, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / "votes.json").write_text(json.dumps({**meta, "unmatched_voters": unmatched, "members": votes}, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / "esop_watch.json").write_text(json.dumps({**meta, "terms": ESOP_TERMS, "bills": esop}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(bills)} tracked bills, votes for {len(votes)} legislators, {len(esop)} ESOP-watch bills")
    if unmatched:
        print("Voters not matched to the roster (check names):", ", ".join(unmatched))


if __name__ == "__main__":
    main()
