"""
Compare two roster snapshots and record what changed in data/changes.json.

Called automatically by scrape_roster.py before it overwrites legislators.json.
You can also run it by hand on two saved files:

    python scraper/roster_changes.py old_legislators.json new_legislators.json
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGES = ROOT / "data" / "changes.json"

TRACKED = {
    "name": "Name",
    "district": "District",
    "party": "Party",
    "leadership_title": "Leadership role",
    "email": "Email",
    "room": "Office",
    "phone": "Phone",
    "status": "Status",
}


def committee_set(m):
    return {(c["chamber"], c["name"], c["role"]) for c in m.get("committees") or []}


def diff(old, new, when=None):
    """Return a list of change records between two legislators.json payloads."""
    when = when or date.today().isoformat()
    old_m = {m["id"]: m for m in old.get("members", [])}
    new_m = {m["id"]: m for m in new.get("members", [])}
    out = []

    def rec(kind, m, detail, **extra):
        out.append({"date": when, "kind": kind, "member_id": m["id"], "name": m["name"],
                    "chamber": m["chamber"], "district": m["district"], "party": m["party"],
                    "detail": detail, **extra})

    if old.get("legislature") != new.get("legislature"):
        out.append({"date": when, "kind": "new_legislature", "member_id": None, "name": None,
                    "chamber": None, "district": None, "party": None,
                    "detail": f"Roster moved from the {old.get('legislature')}th to the {new.get('legislature')}th Legislature"})

    for mid, m in new_m.items():
        if mid not in old_m:
            rec("joined", m, f"Added to the roster ({m['chamber_name']}, LD{m['district']})")
            continue
        o = old_m[mid]
        if o.get("status") == "active" and m.get("status") != "active":
            rec("left", m, m.get("status_note") or "No longer listed as active")
            continue
        for field, label in TRACKED.items():
            if field == "status":
                continue
            if (o.get(field) or None) != (m.get(field) or None):
                rec("updated", m, f"{label}: {o.get(field) or '—'} → {m.get(field) or '—'}", field=field)
        # Committee changes only when both snapshots carry committee data
        if o.get("committees") and m.get("committees"):
            added = committee_set(m) - committee_set(o)
            removed = committee_set(o) - committee_set(m)
            for ch, name, role in sorted(added):
                rec("committee", m, f"Added to {name} ({role})", field="committees")
            for ch, name, role in sorted(removed):
                rec("committee", m, f"Removed from {name} ({role})", field="committees")

    for mid, o in old_m.items():
        if mid not in new_m and o.get("status") == "active":
            rec("left", o, "No longer on the roster")

    return out


def append(records):
    doc = json.loads(CHANGES.read_text(encoding="utf-8")) if CHANGES.exists() else {"changes": []}
    seen = {(c["date"], c["kind"], c["member_id"], c["detail"]) for c in doc["changes"]}
    fresh = [r for r in records if (r["date"], r["kind"], r["member_id"], r["detail"]) not in seen]
    doc["changes"] = sorted(doc["changes"] + fresh, key=lambda c: c["date"], reverse=True)
    CHANGES.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return fresh


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:])
    new = append(diff(a, b))
    print(f"{len(new)} new change(s) recorded in {CHANGES}")
    for r in new:
        print(f"  {r['kind']:<10} {r['name'] or '':<26} {r['detail']}")
